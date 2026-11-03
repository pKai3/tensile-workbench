"""Exercise the missing-Python workflow without downloading or installing Python."""
import hashlib
import os
from pathlib import Path
import shutil
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


@unittest.skipUnless(sys.platform == 'win32', 'native Windows batch workflow')
class WindowsPythonBootstrapTests(unittest.TestCase):
    """Run the real wrappers with synthetic executables; never install Python.

    A native stub preserves all 32 exit-code bits, including the Python install
    manager's 0xA0000006 (-1610612730 in cmd), unlike a POSIX subprocess.
    """

    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix='tensile bootstrap executable ')
        cls.addClassCleanup(temporary.cleanup)
        cls.stub_directory = Path(temporary.name)
        cls.system_directory = Path(os.environ['SystemRoot']) / 'System32'
        cls.command = cls.system_directory / 'cmd.exe'
        cls.stub = cls.stub_directory / 'python.exe'
        source = cls.stub_directory / 'Probe.cs'
        source.write_text(r'''
using System;
using System.IO;
public class Probe {
    public static int Main(string[] args) {
        bool installed = File.Exists(Environment.GetEnvironmentVariable("TW_TEST_INSTALLED"));
        int code = Int32.Parse(Environment.GetEnvironmentVariable(
            installed ? "TW_TEST_AFTER_INSTALL_EXIT" : "TW_TEST_PROBE_EXIT"));
        if (code != 0) {
            Console.Error.WriteLine("[ERROR] No runtime installed. Try running py install.");
            return code;
        }
        if (Array.IndexOf(args, "-c") >= 0) return 0;
        string action = args[args.Length - 1];
        File.AppendAllText(Environment.GetEnvironmentVariable("TW_TEST_LOG"),
                          "action:" + action + "\n");
        return Int32.Parse(Environment.GetEnvironmentVariable(
            action == "setup" ? "TW_TEST_SETUP_EXIT" : "TW_TEST_ACTION_EXIT"));
    }
}
''', encoding='ascii')
        compiler_env = dict(os.environ, TW_TEST_SOURCE=str(source), TW_TEST_EXE=str(cls.stub))
        subprocess.run([
            str(cls.system_directory / 'WindowsPowerShell/v1.0/powershell.exe'),
            '-NoProfile', '-NonInteractive', '-Command',
            "$ErrorActionPreference='Stop'; Add-Type -TypeDefinition "
            "([IO.File]::ReadAllText($env:TW_TEST_SOURCE)) "
            "-OutputAssembly $env:TW_TEST_EXE -OutputType ConsoleApplication",
        ], env=compiler_env, check=True, capture_output=True, text=True, timeout=60)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tensile bootstrap test ')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "code & quotes' checkout"
        self.tools = self.root / 'tools'
        self.tools.mkdir(parents=True)
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        shutil.copy2(self.stub, self.bin / 'py.exe')
        shutil.copy2(self.stub, self.bin / 'python.exe')
        shutil.copy2(TOOLS / 'run_windows.bat', self.tools / 'run_windows.bat')
        for name in ('Install', 'Setup', 'Launch'):
            suffix = '_App' if name == 'Install' else ''
            filename = f'{name}_Tensile_Workbench{suffix}.bat'
            shutil.copy2(ROOT / filename, self.root / filename)
        self.log = self.base / 'events.txt'
        self.installed = self.base / 'installed'
        self.local_app_data = self.base / 'local app data'
        self.installed_python = self.local_app_data / 'Programs/Python/Python314/python.exe'
        # Replace only the actual installation step. Discovery and control flow
        # run unchanged; all candidate folders/PATH are private to this process.
        (self.tools / 'install_python_windows.bat').write_text('''@echo off
>>"%TW_TEST_LOG%" echo installer
if not "%TW_TEST_INSTALL_EXIT%"=="0" exit /b %TW_TEST_INSTALL_EXIT%
type nul > "%TW_TEST_INSTALLED%"
mkdir "%LOCALAPPDATA%\\Programs\\Python\\Python314" >nul 2>&1
copy /y "%TW_TEST_STUB%" "%LOCALAPPDATA%\\Programs\\Python\\Python314\\python.exe" >nul
exit /b 0
'''.replace('\n', '\r\n'), encoding='ascii', newline='')
        self.env = dict(os.environ,
            SYSTEMROOT=str(self.base / 'empty windows'),
            PROGRAMFILES=str(self.base / 'empty program files'),
            LOCALAPPDATA=str(self.local_app_data),
            PATH=str(self.bin) + os.pathsep + str(self.system_directory),
            TENSILE_ENV_DIR=str(self.base / 'environment'),
            TW_TEST_STUB=str(self.stub), TW_TEST_INSTALLED=str(self.installed),
            TW_TEST_LOG=str(self.log), TW_TEST_AFTER_INSTALL_EXIT='0',
            TW_TEST_INSTALL_EXIT='0', TW_TEST_SETUP_EXIT='0', TW_TEST_ACTION_EXIT='0')

    def launch(self, probe_exit, action='Install_Tensile_Workbench_App.bat', **values):
        self.installed.unlink(missing_ok=True)
        self.installed_python.unlink(missing_ok=True)
        self.log.unlink(missing_ok=True)
        env = dict(self.env, TW_TEST_PROBE_EXIT=str(probe_exit), **values)
        result = subprocess.run([str(self.command), '/d', '/c', action], cwd=self.root,
                                env=env, input='\n', capture_output=True, text=True, timeout=30)
        events = self.log.read_text().splitlines() if self.log.exists() else []
        return result, events

    def test_missing_runtime_offers_installer_for_positive_and_hresult_failures(self):
        for code in (1, 103, -1610612730, -1073741515):
            with self.subTest(exit_code=code):
                result, events = self.launch(code)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(events, ['installer', 'action:install-app'])
                self.assertNotIn('[ERROR] No runtime', result.stdout + result.stderr)

    def test_working_runtime_does_not_offer_installation(self):
        result, events = self.launch(0)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(events, ['action:install-app'])

    def test_failed_installer_never_retries_or_runs_setup(self):
        for code in (1, -1610612730):
            with self.subTest(exit_code=code):
                result, events = self.launch(-1610612730, TW_TEST_INSTALL_EXIT=str(code))
                self.assertEqual(result.returncode & 0xffffffff, code & 0xffffffff)
                self.assertEqual(events, ['installer'])

    def test_runtime_still_missing_after_installation_stops_once(self):
        result, events = self.launch(-1610612730, TW_TEST_AFTER_INSTALL_EXIT='-1610612730')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(events, ['installer'])
        self.assertIn('not found after installation', result.stdout)

    def test_launch_builds_environment_after_install_and_stops_on_setup_failure(self):
        for code in (0, 1, -1610612730):
            with self.subTest(exit_code=code):
                result, events = self.launch(-1610612730, 'Launch_Tensile_Workbench_App.bat',
                                             TW_TEST_SETUP_EXIT=str(code))
                self.assertEqual(result.returncode & 0xffffffff, code & 0xffffffff)
                self.assertEqual(events, ['installer', 'action:setup'] +
                                 (['action:desktop'] if code == 0 else []))


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
