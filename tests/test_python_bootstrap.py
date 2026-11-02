"""Exercise the missing-Python workflow without downloading or installing Python."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'


class InstallerMetadataTests(unittest.TestCase):
    def test_release_metadata_has_official_urls_and_complete_checksums(self):
        values = dict(line.split('=', 1) for line in (TOOLS / 'python_installers.conf').read_text().splitlines()
                      if line and not line.startswith('#'))
        version = values['TW_PYTHON_INSTALL_VERSION']
        self.assertTrue(version.startswith('3.14.'))
        for platform, suffix in (('MAC', 'macos11.pkg'), ('WINDOWS', 'amd64.exe')):
            parts = urlsplit(values[f'TW_PYTHON_{platform}_URL'])
            self.assertEqual((parts.scheme, parts.netloc), ('https', 'www.python.org'))
            self.assertEqual(parts.path, f'/ftp/python/{version}/python-{version}-{suffix}')
            self.assertRegex(values[f'TW_PYTHON_{platform}_SHA256'], r'^[0-9a-f]{64}$')


@unittest.skipUnless(sys.platform == 'darwin', 'macOS shell workflow')
class MacPythonBootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tensile bootstrap test ')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.downloads = self.base / 'downloads'
        self.downloads.mkdir()
        self.env = dict(os.environ, TMPDIR=str(self.downloads))

    def shell(self, script, helper='install_python_macos.sh', extra=()):
        return subprocess.run(['/bin/zsh', '-c', 'source "$1"\n' + script,
                               'bootstrap-test', str(TOOLS / helper), *extra],
                              input='\n', capture_output=True, text=True, env=self.env, timeout=10)

    def test_source_and_shell_syntax_do_not_start_installation(self):
        for name in ('install_python_macos.sh', 'run_macos.sh'):
            result = subprocess.run(['/bin/zsh', '-n', str(TOOLS / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        result = self.shell('print -r -- "$TW_PYTHON_INSTALL_VERSION"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout.strip(), r'^3\.14\.\d+$')
        self.assertEqual(list(self.downloads.iterdir()), [])

    def test_cancellation_does_not_download_or_open_installer(self):
        result = self.shell('''
confirm_python_install() { return 1; }
download_python_installer() { print 'UNEXPECTED download'; }
open_python_installer() { print 'UNEXPECTED install'; }
install_python_main
''')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('cancelled', result.stdout)
        self.assertNotIn('UNEXPECTED', result.stdout)
        self.assertEqual(list(self.downloads.iterdir()), [])

    def test_checksum_rejection_cleans_download_and_never_opens_installer(self):
        result = self.shell('''
confirm_python_install() { return 0; }
download_python_installer() { print -rn -- 'wrong installer' > "$1"; }
open_python_installer() { print 'UNEXPECTED install'; }
finish_python_install() { print 'UNEXPECTED completion'; }
install_python_main
''')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('checksum did not match', result.stderr)
        self.assertNotIn('UNEXPECTED', result.stdout)
        self.assertEqual(list(self.downloads.iterdir()), [])

    def test_verified_download_opens_once_then_completes_and_cleans_up(self):
        checksum = hashlib.sha256(b'synthetic installer').hexdigest()
        result = self.shell('''
TW_PYTHON_MAC_SHA256="$2"
confirm_python_install() { return 0; }
download_python_installer() { print -rn -- 'synthetic installer' > "$1"; }
open_python_installer() { [[ -f "$1" ]] || return 99; print 'OPENED'; }
finish_python_install() { print 'FINISHED'; }
install_python_main
''', extra=(checksum,))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('OPENED'), 1)
        self.assertLess(result.stdout.index('OPENED'), result.stdout.index('FINISHED'))
        self.assertEqual(list(self.downloads.iterdir()), [])

    def test_download_or_native_installer_failure_cleans_temporary_files(self):
        checksum = hashlib.sha256(b'synthetic installer').hexdigest()
        for fail_download in (True, False):
            with self.subTest(download=fail_download):
                result = self.shell('''
TW_PYTHON_MAC_SHA256="$2"
confirm_python_install() { return 0; }
download_python_installer() { print -rn -- 'synthetic installer' > "$1"; return ''' +
                    ('1' if fail_download else '0') + '''; }
open_python_installer() { return 1; }
finish_python_install() { print 'UNEXPECTED completion'; }
install_python_main
''', extra=(checksum,))
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertNotIn('UNEXPECTED', result.stdout)
                self.assertEqual(list(self.downloads.iterdir()), [])

    def test_existing_python_skips_bootstrap_and_failed_install_is_not_retried(self):
        available = self.shell('''
find_python() { PYTHON_BIN='/existing/python'; return 0; }
bootstrap_python() { print 'UNEXPECTED install'; return 1; }
ensure_python
print -r -- "$PYTHON_INSTALLED"
''', 'run_macos.sh')
        self.assertEqual(available.returncode, 0, available.stderr)
        self.assertEqual(available.stdout.strip(), '0')
        failed = self.shell('''
find_python() { return 1; }
bootstrap_python() { print 'ATTEMPT'; return 1; }
ensure_python
''', 'run_macos.sh')
        self.assertEqual(failed.returncode, 1, failed.stderr)
        self.assertEqual(failed.stdout.count('ATTEMPT'), 1)

    def test_installation_is_followed_by_rediscovery(self):
        result = self.shell('''
found_count=0
find_python() { ((found_count++)); ((found_count == 2)); }
bootstrap_python() { print 'INSTALLED'; return 0; }
ensure_python || exit 1
print -r -- "$PYTHON_INSTALLED $found_count"
''', 'run_macos.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'INSTALLED\n1 2')

    def test_first_launch_sets_up_packages_before_launch_and_honours_setup_failure(self):
        python = self.base / 'fake python'
        python.write_text('#!/bin/sh\nprintf "%s\\n" "$2" >> "$TW_TEST_LOG"\n'
                          'if [ "$2" = setup ]; then exit "$TW_TEST_SETUP_EXIT"; fi\n')
        python.chmod(0o755)
        log = self.base / 'actions'
        self.env.update(TW_TEST_PYTHON=str(python), TW_TEST_LOG=str(log))
        for setup_code in (0, 7):
            with self.subTest(setup_code=setup_code):
                log.unlink(missing_ok=True)
                self.env['TW_TEST_SETUP_EXIT'] = str(setup_code)
                result = self.shell('''
ensure_python() { PYTHON_BIN="$TW_TEST_PYTHON"; PYTHON_INSTALLED=1; }
run_macos_main launch
''', 'run_macos.sh')
                self.assertEqual(result.returncode, setup_code, result.stderr)
                self.assertEqual(log.read_text().splitlines(), ['setup', 'launch'] if setup_code == 0 else ['setup'])


if __name__ == '__main__':
    unittest.main()
