"""Launcher-only checks; no server, compiler, pip or research data is invoked."""
import importlib.util
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('install_macos_app', ROOT / 'tools/install_macos_app.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class MacAppTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tensile app tests ')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / 'Checkout & spaces'
        self.root.mkdir()
        shutil.copytree(ROOT / 'macos', self.root / 'macos')
        (self.root / 'tools').mkdir()
        for name in ('LICENSE', 'Launch_Tensile_Workbench.command', 'workbench_environment.py',
                     'workbench_server.py', 'tools/run_macos.sh'):
            shutil.copyfile(ROOT / name, self.root / name)
        self.build_dir = self.base / 'build'
        self.build_dir.mkdir()
        self.destination = self.base / 'Applications' / installer.APP_NAME
        self.backups = self.base / 'backups'

    def fake_build(self, architecture='arm64', environ=None):
        def command(args, **kwargs):
            if 'swiftc' in args:
                Path(args[args.index('-o') + 1]).write_bytes(b'fake executable')
            return subprocess.CompletedProcess(args, 0, stdout='', stderr='')
        with patch.object(installer, 'run', side_effect=command) as calls:
            app = installer.build_bundle(self.root, self.build_dir,
                                         environ={} if environ is None else environ,
                                         architecture=architecture)
        return app, calls

    def test_build_injects_paths_only_in_generated_plist_and_uses_native_architecture(self):
        before = (self.root / 'macos/Info.plist').read_bytes()
        app, calls = self.fake_build('x86_64')
        metadata = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        self.assertEqual(metadata['WorkbenchLauncherPath'], str(self.root / 'Launch_Tensile_Workbench.command'))
        self.assertNotIn('WorkbenchEnvironmentPath', metadata)
        self.assertEqual((self.root / 'macos/Info.plist').read_bytes(), before)
        self.assertNotIn('WorkbenchLauncherPath', plistlib.loads(before))
        self.assertEqual((app / 'Contents/Resources/Launcher.swift').read_bytes(),
                         (self.root / 'macos/Launcher.swift').read_bytes())
        self.assertTrue((app / 'Contents/Resources/LICENSE').is_file())
        commands = [call.args[0] for call in calls.call_args_list]
        self.assertIn('x86_64-apple-macos13.0', commands[0])
        self.assertIn(self.build_dir / 'module-cache', commands[0])
        self.assertEqual(commands[-1][1:3], ['--verify', '--strict'])
        self.assertFalse((self.root / 'data').exists())
        self.assertFalse((self.root / 'output').exists())

    def test_custom_environment_recorded_for_finder(self):
        environment = self.base / 'local environment/venv'
        app, _ = self.fake_build(environ={'TENSILE_ENV_DIR': str(environment)})
        metadata = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        self.assertEqual(metadata['WorkbenchEnvironmentPath'], str(environment))
        self.assertFalse(environment.exists())

    def test_invalid_custom_environment_does_not_compile(self):
        for location in ('./relative', str(self.root / '.venv'), str(self.base / 'OneDrive/venv')):
            with self.subTest(location=location), patch.object(installer, 'run') as run:
                with self.assertRaises(ValueError):
                    installer.build_bundle(self.root, self.build_dir,
                                           environ={'TENSILE_ENV_DIR': location}, architecture='arm64')
                run.assert_not_called()

    def test_running_app_is_blocked_without_stopping_it(self):
        for command in ('/some user/Applications/Tensile Workbench.app/Contents/MacOS/TensileWorkbench',
                        'TensileWorkbench'):
            with self.subTest(command=command), patch.object(installer, 'run', return_value=
                    subprocess.CompletedProcess([], 0, stdout=command + '\n')) as run:
                with self.assertRaisesRegex(RuntimeError, 'Quit Tensile Workbench'):
                    installer.check_app_stopped()
                self.assertEqual(run.call_args.args[0], ['/bin/ps', '-axo', 'comm='])
        with patch.object(installer, 'run', side_effect=subprocess.CalledProcessError(1, 'ps')):
            with self.assertRaises(subprocess.CalledProcessError):
                installer.check_app_stopped()  # Fail closed if process inspection fails.

    def test_new_install_and_update_preserve_dock_directory_and_backup(self):
        app, _ = self.fake_build()
        with patch.object(installer, 'check_app_stopped'), patch.object(installer, 'run'):
            self.assertIsNone(installer.install_bundle(app, self.destination, self.backups))
            before_inode = self.destination.stat().st_ino
            old_binary = self.destination / 'Contents/MacOS/TensileWorkbench'
            old_binary.write_bytes(b'old executable')
            backup = installer.install_bundle(app, self.destination, self.backups)
        self.assertEqual(self.destination.stat().st_ino, before_inode)
        self.assertEqual((backup / 'Contents/MacOS/TensileWorkbench').read_bytes(), b'old executable')
        self.assertEqual(old_binary.read_bytes(), b'fake executable')
        self.assertEqual(list(self.destination.parent.glob('.tensile-install-*')), [])

    def test_failed_swap_restores_original(self):
        app, _ = self.fake_build()
        shutil.copytree(app, self.destination)
        binary = self.destination / 'Contents/MacOS/TensileWorkbench'
        binary.write_bytes(b'keep me')
        with patch.object(installer, 'check_app_stopped'), patch.object(installer, 'run'), \
             patch.object(Path, 'replace', side_effect=OSError('simulated swap failure')):
            with self.assertRaisesRegex(OSError, 'simulated swap failure'):
                installer.install_bundle(app, self.destination, self.backups)
        self.assertEqual(binary.read_bytes(), b'keep me')

    def test_unrecognised_destination_and_symlink_are_not_overwritten(self):
        self.destination.mkdir(parents=True)
        sentinel = self.destination / 'leave alone'
        sentinel.write_text('original')
        with self.assertRaisesRegex(RuntimeError, 'unrecognised'):
            installer.validate_destination(self.destination)
        link = self.base / 'linked.app'
        link.symlink_to(self.destination, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'symlink'):
            installer.validate_destination(link)
        self.assertEqual(sentinel.read_text(), 'original')

    def test_absent_build_tools_give_recovery_instructions(self):
        with patch.object(installer.sys, 'platform', 'darwin'), \
             patch.object(installer.platform, 'mac_ver', return_value=('13.0', '', '')), \
             patch.object(installer, 'run', side_effect=subprocess.CalledProcessError(1, 'xcode-select')):
            with self.assertRaisesRegex(RuntimeError, 'xcode-select --install'):
                installer.require_build_tools()

    def test_temporary_compiler_cache_removed_on_build_failure(self):
        created = []
        def fail_build(root, directory):
            created.append(Path(directory))
            cache = Path(directory) / 'module-cache'
            cache.mkdir()
            (cache / 'temporary').write_text('compiler output')
            raise RuntimeError('synthetic compiler failure')
        with patch.object(installer, 'require_build_tools'), patch.object(installer, 'check_app_stopped'), \
             patch.object(Path, 'home', return_value=self.base / 'user'), \
             patch.object(installer, 'build_bundle', side_effect=fail_build):
            with self.assertRaisesRegex(RuntimeError, 'synthetic compiler failure'):
                installer.main()
        self.assertTrue(created)
        self.assertFalse(created[0].exists())
        self.assertFalse((self.base / 'user/Applications').exists())

    @unittest.skipUnless(sys.platform == 'darwin', 'Mac wrapper check')
    def test_shell_setup_and_app_only_flow(self):
        for name in ('Setup_Tensile_Workbench.command', 'Install_Tensile_Workbench_App.command',
                     'Launch_Tensile_Workbench.command', 'tools/run_macos.sh'):
            subprocess.run(['/bin/zsh', '-n', str(ROOT / name)], check=True)
        for name in ('Setup_Tensile_Workbench.command', 'Install_Tensile_Workbench_App.command'):
            shutil.copyfile(ROOT / name, self.root / name)
        environment = self.base / 'venv'
        fake = environment / 'bin/python'
        fake.parent.mkdir(parents=True)
        fake.write_text('#!/bin/sh\nif [ "$1" = "-c" ]; then exit 0; fi\n'
                        'printf "%s\\n" "$@"\n'
                        'case "$1" in *install_macos_app.py) exit 9;; esac\nexit 0\n')
        fake.chmod(0o755)
        env = dict(os.environ, TENSILE_ENV_DIR=str(environment))
        result = subprocess.run(['/bin/zsh', str(self.root / 'Setup_Tensile_Workbench.command')],
                                env=env, input='\n', text=True, capture_output=True, cwd=self.base)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Python setup succeeded', result.stdout)
        self.assertIn(str(self.root / 'tools/install_macos_app.py'), result.stdout)
        result = subprocess.run(['/bin/zsh', str(self.root / 'Install_Tensile_Workbench_App.command')],
                                env=env, input='\n', text=True, capture_output=True, cwd=self.base)
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertNotIn('workbench_environment.py', result.stdout)


if __name__ == '__main__':
    unittest.main()
