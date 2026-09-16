from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import venv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import workbench_environment as environment


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tensile setup test ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'code with spaces'
        self.root.mkdir()
        for source in ROOT.glob('*.py'):
            shutil.copy2(source, self.root / source.name)
        for name in ('requirements.txt', 'requirements-windows.txt',
                     'tensile_workbench_defaults.json', 'tensile_workbench.ipynb'):
            shutil.copy2(ROOT / name, self.root / name)
        self.folder = self.base / 'local support' / 'venv'
        self.folder.parent.mkdir()
        self.local = self.base / 'LocalAppData'

    def fake_python(self, system, folder=None):
        python = environment.python_in(folder or self.folder, system)
        python.parent.mkdir(parents=True, exist_ok=True)
        python.touch()
        return python

    def test_new_defaults_outside_repository_for_both_systems(self):
        mac = environment.environment_folder(self.root, 'darwin', {}, self.base / 'user')
        self.assertEqual(mac, self.base / 'user/Library/Application Support/Tensile Workbench/venv')
        win = environment.environment_folder(self.root, 'win32', {'LOCALAPPDATA': str(self.local)})
        self.assertEqual(win, self.local / 'TensileWorkbench/venv')
        for folder in (mac, win):
            environment.validate_environment_location(folder, self.root, {})
            self.assertFalse(folder.exists())

    def test_legacy_windows_reuse_for_zip_and_git_line_endings(self):
        raw = (self.root / 'requirements-windows.txt').read_bytes().replace(b'\r\n', b'\n')
        for legacy_raw, checkout_raw in ((raw, raw.replace(b'\n', b'\r\n')),
                                         (raw.replace(b'\n', b'\r\n'), raw)):
            with self.subTest(legacy_raw=legacy_raw[:40]):
                key = hashlib.sha256(legacy_raw).hexdigest()[:12]
                base = self.local / key
                expected = base / 'TensileWorkbench' / ('v17-py313-' + key) / 'venv'
                self.fake_python('win32', expected)
                (self.root / 'requirements-windows.txt').write_bytes(checkout_raw)
                folder = environment.environment_folder(self.root, 'win32', {'LOCALAPPDATA': str(base)})
                self.assertEqual(folder, expected)

    def test_canonical_windows_folder_is_preferred_even_when_partial(self):
        canonical = self.local / 'TensileWorkbench/venv'
        canonical.mkdir(parents=True)
        self.assertEqual(environment.environment_folder(self.root, 'win32', {'LOCALAPPDATA': str(self.local)}), canonical)

    def test_override_and_unsafe_locations(self):
        for system in ('win32', 'darwin'):
            self.assertEqual(environment.environment_folder(self.root, system, {'TENSILE_ENV_DIR': str(self.folder)}), self.folder)
        with self.assertRaisesRegex(ValueError, 'absolute'):
            environment.environment_folder(self.root, 'darwin', {'TENSILE_ENV_DIR': './venv'})
        for folder in (self.root, self.root / '.venv', self.base,
                       self.base / 'OneDrive - University/venv', self.base / 'Library/CloudStorage/X/venv'):
            with self.subTest(folder=folder), self.assertRaises(ValueError):
                environment.validate_environment_location(folder, self.root, {})
        with self.assertRaises(ValueError):
            environment.validate_environment_location(self.base / 'renamed sync/venv', self.root,
                                                       {'OneDriveCommercial': str(self.base / 'renamed sync')})

    def test_missing_windows_localappdata_is_actionable(self):
        with self.assertRaisesRegex(RuntimeError, 'LOCALAPPDATA'):
            environment.environment_folder(self.root, 'win32', {})

    def test_caches_are_external_and_python_injection_is_cleared(self):
        with patch.dict(os.environ, {'PYTHONHOME': '/wrong', 'PYTHONPATH': '/wrong', 'PYTHONPYCACHEPREFIX': '/wrong'}):
            env = environment.child_environment(self.folder)
        for key in ('PYTHONHOME', 'PYTHONPATH', 'PYTHONPYCACHEPREFIX'):
            self.assertNotIn(key, env)
        for key in ('JUPYTER_CONFIG_DIR', 'JUPYTER_DATA_DIR', 'JUPYTER_RUNTIME_DIR', 'IPYTHONDIR', 'MPLCONFIGDIR'):
            self.assertTrue(Path(env[key]).is_relative_to(self.folder.parent))
        self.assertEqual(env['PYTHONDONTWRITEBYTECODE'], '1')

    def test_setup_creates_once_reuses_and_preserves_project(self):
        sentinel = self.root / 'tensile_workbench.project.json'
        sentinel.write_text('{"test": "untouched"}')
        before = sentinel.read_bytes()
        for system in ('darwin', 'win32'):
            folder = self.folder.parent / system / 'venv'
            folder.parent.mkdir()
            def create(target):
                self.fake_python(system, target)
            with patch.object(environment.venv, 'EnvBuilder') as builder, \
                 patch.object(environment.subprocess, 'run') as run, \
                 patch.object(environment.subprocess, 'check_output', return_value='synthetic==1\n'), \
                 redirect_stdout(io.StringIO()):
                builder.return_value.create.side_effect = create
                environment.setup(folder, self.root, system)
                environment.setup(folder, self.root, system)
            builder.return_value.create.assert_called_once_with(folder)
            builder.assert_called_once_with(with_pip=True)
            commands = [call.args[0] for call in run.call_args_list]
            installs = [command for command in commands if command[1:4] == ['-m', 'pip', 'install']]
            self.assertEqual(len(installs), 2)
            self.assertIn('--no-cache-dir', installs[0])
            self.assertIn('--only-binary=:all:', installs[0])
            self.assertNotIn('--upgrade', installs[0])
            self.assertEqual(installs[0][-1], str(self.root / 'requirements.txt'))
            self.assertEqual(commands[0][2], environment.RUNTIME_CHECK)
            self.assertTrue(any(environment.CHECK in command for command in commands))
            self.assertTrue(any('--sys-prefix' in command and 'python3' in command for command in commands))
            self.assertFalse(any('jupyterlab' in command for command in commands))
            self.assertTrue((folder.parent / 'setup-complete.json').is_file())
        self.assertEqual(sentinel.read_bytes(), before)
        self.assertFalse((self.root / 'output').exists())

    def test_failure_does_not_claim_success_or_launch(self):
        self.fake_python('darwin')
        with patch.object(environment.subprocess, 'run', side_effect=[None, subprocess.CalledProcessError(1, 'pip')]) as run, \
             patch.object(environment.subprocess, 'check_output') as freeze, redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):
                environment.setup(self.folder, self.root, 'darwin')
        self.assertEqual(run.call_count, 2)
        freeze.assert_not_called()
        self.assertFalse((self.folder.parent / 'setup-complete.json').exists())

    def test_wrong_environment_fails_before_pip(self):
        self.fake_python('darwin')
        with patch.object(environment.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'check')) as run, \
             redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):
                environment.setup(self.folder, self.root, 'darwin')
        self.assertEqual(run.call_count, 1)
        self.assertNotIn('pip', run.call_args.args[0])

    def test_partial_environment_is_not_overwritten(self):
        self.folder.mkdir()
        sentinel = self.folder / 'keep'
        sentinel.write_text('keep')
        with patch.object(environment.venv, 'EnvBuilder') as builder, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'not overwritten'):
                environment.setup(self.folder, self.root, 'darwin')
        builder.assert_not_called()
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_launch_uses_selected_interpreter_from_any_cwd_and_does_not_install(self):
        for system in ('darwin', 'win32'):
            python = self.fake_python(system)
            with patch.object(environment, 'require_runtime'), patch.object(environment.sys, 'platform', system), \
                 patch.dict(os.environ, {'TENSILE_ENV_DIR': str(self.folder)}), \
                 patch.object(environment.subprocess, 'run') as run, \
                 patch.object(environment.venv, 'EnvBuilder') as builder, redirect_stdout(io.StringIO()):
                self.assertEqual(environment.main(['launch'], self.root), 0)
            builder.assert_not_called()
            self.assertEqual(run.call_count, 2)
            self.assertIn(environment.QUICK_CHECK, run.call_args_list[0].args[0])
            self.assertEqual(run.call_args_list[-1].args[0], [str(python), str(self.root / 'launch_workbench.py')])
            self.assertEqual(run.call_args.kwargs['cwd'], self.root)
            self.assertFalse(any('pip' in call.args[0] for call in run.call_args_list))

    def test_missing_environment_tells_user_to_run_setup(self):
        with patch.object(environment, 'require_runtime'), \
             patch.dict(os.environ, {'TENSILE_ENV_DIR': str(self.folder)}), \
             patch.object(environment.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Run Setup_Tensile_Workbench'):
                environment.main(['launch'], self.root)
        run.assert_not_called()

    def test_check_does_not_launch_or_install(self):
        self.fake_python(sys.platform)
        with patch.object(environment, 'require_runtime'), \
             patch.dict(os.environ, {'TENSILE_ENV_DIR': str(self.folder)}), \
             patch.object(environment.subprocess, 'run') as run, redirect_stdout(io.StringIO()):
            self.assertEqual(environment.main(['check'], self.root), 0)
        self.assertEqual(run.call_count, 1)
        self.assertIn(environment.CHECK, run.call_args.args[0])

    def test_quick_check_does_not_import_numerical_ui_or_application_stack(self):
        guard = r'''
import sys
blocked = {'numpy', 'pandas', 'matplotlib', 'openpyxl', 'ipywidgets', 'jupyterlab',
           'voila', 'ipykernel', 'plotly', 'anywidget', 'tensile_core', 'tensile_workbench'}
def reject_heavy_import(event, args):
    if event == 'import' and args[0].split('.')[0] in blocked:
        raise RuntimeError('Preflight imported ' + args[0])
sys.addaudithook(reject_heavy_import)
'''
        result = subprocess.run([sys.executable, '-c', guard + environment.QUICK_CHECK,
                                 str(self.root), sys.prefix], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Dependencies and saved definitions OK', result.stdout)
        self.assertFalse((self.root / 'data').exists())
        self.assertFalse((self.root / 'output').exists())

    def test_quick_check_still_rejects_invalid_definitions_and_dependencies(self):
        project = self.root / 'tensile_workbench.project.json'
        project.write_text('{"schema_version": -1}')
        command = [sys.executable, '-c', environment.QUICK_CHECK, str(self.root), sys.prefix]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unsupported workbench project schema', result.stderr)
        self.assertEqual(project.read_text(), '{"schema_version": -1}')
        (self.root / 'requirements.txt').write_text('numpy>=999\n')
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('run Setup again', result.stderr)

    def test_preflight_reports_missing_and_cloud_only_files(self):
        environment.check_project_files(self.root)
        real_stat = Path.stat
        def cloud_stat(path, *args, **kwargs):
            info = real_stat(path, *args, **kwargs)
            if path == self.root / 'tensile_core.py':
                return SimpleNamespace(st_mode=info.st_mode, st_flags=0x40000000)
            return info
        with patch.object(Path, 'stat', cloud_stat), patch.object(stat, 'SF_DATALESS', 0x40000000, create=True):
            with self.assertRaisesRegex(RuntimeError, 'tensile_core.py.*online-only'):
                environment.check_project_files(self.root)
        (self.root / 'tensile_core.py').unlink()
        with self.assertRaisesRegex(RuntimeError, 'tensile_core.py.*missing'):
            environment.check_project_files(self.root)

    @unittest.skipUnless(sys.platform == 'darwin', 'Mac interpreter smoke test')
    def test_real_minimal_venv_runtime_without_installing_packages(self):
        # Tiny temporary venv without pip: no network or changes to user environment.
        venv.EnvBuilder(with_pip=False).create(self.folder)
        python = environment.python_in(self.folder, 'darwin')
        result = subprocess.run([str(python), '-c', environment.RUNTIME_CHECK, str(ROOT), str(self.folder)],
                                env=environment.child_environment(self.folder), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrapper_targets_and_mac_shell_syntax(self):
        for name, action in (('Setup_Tensile_Workbench', 'setup'), ('Launch_Tensile_Workbench', 'launch')):
            self.assertIn('run_windows.bat" ' + action, (ROOT / (name + '.bat')).read_text())
            self.assertIn('run_macos.sh" ' + action, (ROOT / (name + '.command')).read_text())
        if sys.platform == 'darwin':
            for name in ('Setup_Tensile_Workbench.command', 'Launch_Tensile_Workbench.command', 'tools/run_macos.sh'):
                subprocess.run(['/bin/zsh', '-n', str(ROOT / name)], check=True)

    @unittest.skipUnless(sys.platform == 'darwin', 'Mac wrapper smoke test')
    def test_mac_double_click_wrappers_preserve_spaces_and_failure_codes(self):
        tools = self.root / 'tools'
        tools.mkdir()
        shutil.copy2(ROOT / 'tools/run_macos.sh', tools / 'run_macos.sh')
        fake = self.fake_python('darwin')
        fake.write_text('#!/bin/sh\nif [ "$1" = "-c" ]; then exit 0; fi\nprintf "%s\\n" "$@"\nexit 7\n')
        fake.chmod(0o755)
        for name, action in (('Setup_Tensile_Workbench.command', 'setup'),
                             ('Launch_Tensile_Workbench.command', 'launch')):
            shutil.copy2(ROOT / name, self.root / name)
            env = dict(os.environ, TENSILE_ENV_DIR=str(self.folder))
            result = subprocess.run(['/bin/zsh', str(self.root / name)], cwd=self.base,
                                    env=env, input='\n', capture_output=True, text=True)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertIn(str(self.root / 'workbench_environment.py') + '\n' + action, result.stdout)

    def test_runtime_rejects_wrong_python_and_free_threaded_build(self):
        for version, disabled in (((3, 12), False), ((3, 13), True)):
            with patch.object(environment.sys, 'platform', 'darwin'), \
                 patch.object(environment.sys, 'version_info', version), \
                 patch.object(environment.platform, 'machine', return_value='arm64'), \
                 patch.object(environment.sysconfig, 'get_config_var', return_value=disabled):
                with self.assertRaisesRegex(RuntimeError, 'Python 3.13'):
                    environment.require_runtime()


if __name__ == '__main__':
    unittest.main()
