"""Update real synthetic installations only; never install packages or run research."""
import copy
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import workbench_updates as updates
from tools import build_release, update_bridge, update_workbench
import workbench_environment as environment


def source(number='1.0.0'):
    return {'VERSION': (number + '\n').encode(), 'requirements.txt': b'example>=1\n',
            'workbench_environment.py': b'# Synthetic bootstrap\n',
            'tools/update_workbench.py': b'# Synthetic helper\n',
            'app.py': ('print("' + number + '")\n').encode()}


def manifest(contents, number='1.0.0', commit='a' * 40):
    return {'format': updates.FORMAT, 'version': number, 'python': '3.14', 'commit': commit,
            'files': {name: {'sha256': updates.sha256(raw), 'mode': 0o644}
                      for name, raw in contents.items()}}


def install(root, contents, number='1.0.0'):
    root.mkdir(parents=True, exist_ok=True)
    for name, raw in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    value = manifest(contents, number)
    updates.write_json(root / updates.MANIFEST, value)
    return value


def archive(path, contents, number='1.1.0', value=None):
    value = value or manifest(contents, number)
    with zipfile.ZipFile(path, 'w') as output:
        for name, raw in contents.items():
            output.writestr(name, raw)
        output.writestr(updates.MANIFEST, json.dumps(value))
    return value


class UpdateFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tensile updates & spaces ')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / 'App'
        self.old = source()
        self.old['obsolete.py'] = b'old feature\n'
        self.baseline = install(self.root, self.old)
        self.incoming = source('1.1.0')
        self.incoming['new.py'] = b'new feature\n'
        self.directory = self.base / 'updates/transaction'
        self.stage = self.directory / 'source'
        self.next_manifest = install(self.stage, self.incoming, '1.1.0')
        self.folder = self.base / 'environment'
        self.plan = {'root': str(self.root), 'directory': str(self.directory), 'stage': str(self.stage),
                     'baseline': self.baseline, 'incoming': self.next_manifest, 'git': False,
                     'environment': str(self.base / 'new-environment'),
                     'previous_environment': str(self.folder), 'state': 'prepared'}
        updates.write_json(self.directory / 'transaction.json', self.plan)

    def apply(self, **kwargs):
        updates.apply_update(self.plan, **kwargs)


class UpdateTests(UpdateFixture):
    def test_install_preserves_settings_unknown_files_and_research(self):
        saved = {'tensile_workbench.project.json': b'{"personal": "unchanged"}',
                 '.tensile-paths.json': b'{"data": "outside"}',
                 'my_notes.txt': b'keep me', 'data/test.csv': b'unique research',
                 'output/result.xlsx': b'unique output'}
        for name, raw in saved.items():
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_bytes(raw)
        self.apply()
        self.assertEqual(updates.installed_version(self.root), '1.1.0')
        for name, raw in saved.items():
            self.assertEqual((self.root / name).read_bytes(), raw)
        self.assertFalse((self.root / 'obsolete.py').exists())
        self.assertEqual((self.root / 'new.py').read_bytes(), self.incoming['new.py'])
        self.assertEqual((self.directory / 'saved-settings/tensile_workbench.project.json').read_bytes(), saved['tensile_workbench.project.json'])
        self.assertFalse((self.directory / 'backup/data').exists())
        self.assertEqual(environment.environment_folder(self.root, environ={}), Path(self.plan['environment']))
        self.assertFalse((self.root / updates.LOCK).exists())

    def test_activation_failure_rolls_back_code_pointer_and_launcher(self):
        pointer = b'{"schema_version":1,"environment":"/previous"}'
        (self.root / updates.POINTER).write_bytes(pointer)
        restored = []
        with self.assertRaisesRegex(RuntimeError, 'cannot activate'):
            self.apply(activate=lambda plan: (_ for _ in ()).throw(RuntimeError('cannot activate')),
                       restore_launcher=lambda plan: restored.append(True))
        self.assertEqual(self.plan['state'], 'rolled-back')
        self.assertEqual(restored, [True])
        for name, raw in self.old.items():
            self.assertEqual((self.root / name).read_bytes(), raw)
        self.assertFalse((self.root / 'new.py').exists())
        self.assertEqual((self.root / updates.POINTER).read_bytes(), pointer)
        self.assertFalse((self.root / updates.LOCK).exists())

    def test_recovery_never_rewinds_personal_settings(self):
        self.apply()
        path = self.root / 'tensile_workbench.project.json'
        path.write_bytes(b'later personal edits')
        updates.rollback_update(self.plan)
        self.assertEqual(path.read_bytes(), b'later personal edits')
        self.assertEqual(updates.installed_version(self.root), '1.0.0')

    def test_changed_code_or_unknown_colliding_file_is_not_overwritten(self):
        for name in ('app.py', 'new.py'):
            with self.subTest(name=name):
                original = (self.root / name).read_bytes() if (self.root / name).exists() else None
                (self.root / name).write_bytes(b'my changes')
                with self.assertRaises(updates.UpdateError):
                    self.apply()
                self.assertEqual((self.root / name).read_bytes(), b'my changes')
                self.assertFalse((self.root / updates.LOCK).exists())
                if original is None:
                    (self.root / name).unlink()
                else:
                    (self.root / name).write_bytes(original)

    def test_changed_code_during_recovery_and_corrupt_backup_are_rejected(self):
        self.apply()
        (self.root / 'app.py').write_bytes(b'new local edits')
        with self.assertRaisesRegex(updates.UpdateError, 'edited after'):
            updates.rollback_update(self.plan)
        self.assertEqual(updates.installed_version(self.root), '1.1.0')
        (self.root / 'app.py').write_bytes(self.incoming['app.py'])
        (self.directory / 'backup/obsolete.py').write_bytes(b'corrupt')
        with self.assertRaisesRegex(updates.UpdateError, 'checksum failed'):
            updates.rollback_update(self.plan)
        self.assertEqual(updates.installed_version(self.root), '1.1.0')

    def test_crash_before_code_write_can_release_recovery_lock(self):
        (self.root / updates.LOCK).write_text('{}')
        updates.rollback_update(self.plan)
        self.assertEqual(updates.installed_version(self.root), '1.0.0')
        self.assertFalse((self.root / updates.LOCK).exists())

    def test_existing_transaction_is_not_stolen(self):
        (self.root / updates.LOCK).write_text('another transaction')
        with self.assertRaises(FileExistsError):
            self.apply()
        self.assertEqual((self.root / updates.LOCK).read_text(), 'another transaction')

    def test_partial_write_failure_restores_previous_code(self):
        real = updates.atomic_write
        failed = False
        def fail_once(path, raw):
            nonlocal failed
            if Path(path) == self.root / 'app.py' and not failed:
                failed = True
                raise OSError('simulated disk error')
            real(path, raw)
        with patch.object(updates, 'atomic_write', side_effect=fail_once):
            with self.assertRaisesRegex(OSError, 'disk error'):
                self.apply()
        for name, raw in self.old.items():
            self.assertEqual((self.root / name).read_bytes(), raw)

    def test_linked_source_path_is_rejected_but_research_link_is_untouched(self):
        outside = self.base / 'research'
        outside.mkdir()
        (outside / 'curve.csv').write_bytes(b'precious')
        try:
            (self.root / 'data').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Creating symlinks is not available to this Windows user.')
        self.apply()
        self.assertEqual((outside / 'curve.csv').read_bytes(), b'precious')
        updates.rollback_update(self.plan)
        (self.root / 'app.py').unlink()
        (self.root / 'app.py').symlink_to(outside / 'curve.csv')
        with self.assertRaisesRegex(updates.UpdateError, 'linked path'):
            self.apply()
        self.assertEqual((outside / 'curve.csv').read_bytes(), b'precious')

    def test_archive_checksum_contents_and_modes(self):
        path = self.base / 'valid.zip'
        value = manifest(self.incoming, '1.1.0')
        value['files']['app.py']['mode'] = 0o755
        archive(path, self.incoming, value=value)
        target = self.base / 'unpacked'
        self.assertEqual(updates.unpack_release(path, target, '1.1.0'), value)
        self.assertEqual((target / 'app.py').read_bytes(), self.incoming['app.py'])
        if os.name != 'nt':
            self.assertTrue((target / 'app.py').stat().st_mode & stat.S_IXUSR)

    def test_unsafe_archive_and_personal_paths_never_extract(self):
        for name in ('../escape', '/absolute', 'C:/drive', 'folder\\escape', 'a/../b',
                     'NUL.py', 'a./b', 'data/curve.csv', '.git/config',
                     'tensile_workbench.project.json', '.tensile-paths.json'):
            with self.subTest(name=name):
                contents = {**self.incoming, name: b'no'}
                path = self.base / 'unsafe.zip'
                archive(path, contents)
                with self.assertRaises(updates.UpdateError):
                    updates.unpack_release(path, self.base / 'unsafe', '1.1.0')
                self.assertFalse((self.base / 'unsafe').exists())

    def test_duplicate_case_symlink_and_tampered_archive_rejected(self):
        for kind in ('duplicate-case', 'symlink', 'checksum', 'unexpected'):
            with self.subTest(kind=kind):
                path = self.base / 'bad.zip'
                value = manifest(self.incoming, '1.1.0')
                contents = dict(self.incoming)
                if kind == 'checksum':
                    contents['app.py'] = b'tampered'
                archive(path, contents, value=value)
                with zipfile.ZipFile(path, 'a') as package:
                    if kind == 'duplicate-case':
                        package.writestr('APP.py', b'no')
                    if kind == 'unexpected':
                        package.writestr('extra.py', b'no')
                    if kind == 'symlink':
                        info = zipfile.ZipInfo('linked')
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                        package.writestr(info, b'/outside')
                with self.assertRaises(updates.UpdateError):
                    updates.unpack_release(path, self.base / 'bad', '1.1.0')
                self.assertFalse((self.base / 'bad').exists())

    def test_release_metadata_requires_official_asset_and_digest(self):
        payload = {'tag_name': 'v1.1.0', 'assets': [{'name': 'Tensile-Workbench-1.1.0.zip',
            'browser_download_url': 'https://github.com/pKai3/tensile-workbench/releases/download/v1.1.0/Tensile-Workbench-1.1.0.zip',
            'size': 123, 'digest': 'sha256:' + 'f' * 64}]}
        self.assertEqual(updates.release_info(payload)['version'], '1.1.0')
        for change in ({'digest': ''}, {'size': 0}, {'browser_download_url': 'https://other.invalid/update.zip'}):
            bad = copy.deepcopy(payload)
            bad['assets'][0].update(change)
            with self.assertRaises(updates.UpdateError):
                updates.release_info(bad)
        payload['prerelease'] = True
        with self.assertRaises(updates.UpdateError):
            updates.release_info(payload)

    def test_version_order_is_numeric_and_cannot_downgrade(self):
        release = {'version': '1.10.0'}
        (self.root / 'VERSION').write_text('1.9.0')
        with patch.object(updates, 'fetch_json'), patch.object(updates, 'release_info', return_value=release):
            self.assertTrue(updates.check_release(self.root)['available'])
            (self.root / 'VERSION').write_text('2.0.0')
            self.assertFalse(updates.check_release(self.root)['available'])

    def test_download_truncation_and_digest_failure_remove_partial_file(self):
        import io
        class Response(io.BytesIO):
            url = 'https://github.com/release'
        for raw, expected_size, digest in ((b'partial', 20, 'a' * 64), (b'full', 4, 'b' * 64),
                                          (b'too long', 2, 'c' * 64)):
            path = self.base / 'download.zip'
            with patch.object(updates, 'urlopen', return_value=Response(raw)):
                with self.assertRaises(updates.UpdateError):
                    updates.download_release({'url': 'https://github.com/release', 'size': expected_size, 'sha256': digest}, path)
            self.assertFalse(path.exists())

    def test_shutdown_requires_acknowledgement_and_actual_parent_exit(self):
        session = self.base / 'session.json'
        updates.write_json(session, {'nonce': 'secret', 'pid': 42})
        updates.write_json(self.base / 'stopped.json', {'nonce': 'secret'})
        with patch.object(updates, 'process_alive', return_value=False):
            updates.wait_for_shutdown(session, timeout=1)
        with patch.object(updates, 'process_alive', return_value=True):
            with self.assertRaisesRegex(updates.UpdateError, 'did not finish'):
                updates.wait_for_shutdown(session, timeout=.01)
        updates.write_json(self.base / 'stopped.json', {'nonce': 'wrong'})
        with patch.object(updates, 'process_alive', return_value=False):
            with self.assertRaises(updates.UpdateError):
                updates.wait_for_shutdown(session, timeout=.01)

    def test_bridge_needs_nonce_live_helper_and_matching_action(self):
        with patch.object(update_bridge, 'update_directory', return_value=self.base / 'sessions'):
            bridge = update_bridge.UpdateBridge(self.root, self.folder)
        from unittest.mock import Mock
        bridge.helper = Mock()
        bridge.helper.poll.return_value = None
        request = bridge.directory / 'request.json'
        updates.write_json(request, {'nonce': 'wrong', 'action': 'stop-for-update'})
        self.assertFalse(bridge.stop_requested())
        updates.write_json(request, {'nonce': bridge.nonce, 'action': 'stop-for-update'})
        self.assertTrue(bridge.stop_requested())
        bridge.helper.poll.return_value = 0
        self.assertFalse(bridge.stop_requested())

    def test_active_environment_is_validated_and_explicit_override_wins(self):
        updates.write_json(self.root / updates.POINTER, {'schema_version': 1, 'environment': str(self.folder)})
        self.assertEqual(environment.environment_folder(self.root, environ={}), self.folder)
        custom = self.base / 'custom'
        self.assertEqual(environment.environment_folder(self.root, environ={'TENSILE_ENV_DIR': str(custom)}), custom)
        updates.write_json(self.root / updates.POINTER, {'schema_version': 1, 'environment': str(self.root / 'venv')})
        with self.assertRaisesRegex(RuntimeError, 'invalid'):
            environment.environment_folder(self.root, environ={})

    def test_startup_refuses_incomplete_update(self):
        (self.root / updates.LOCK).write_text('{}')
        with self.assertRaisesRegex(RuntimeError, 'update is in progress'):
            environment.check_project_files(self.root)

    def test_current_process_liveness_on_native_platform(self):
        self.assertTrue(updates.process_alive(os.getpid()))
        self.assertFalse(updates.process_alive(-1))

    def test_prepare_reuses_environment_and_does_not_modify_live_code(self):
        path = self.base / 'update.zip'
        archive(path, self.incoming)
        def download(release, target):
            shutil.copyfile(path, target)
        with patch.object(updates, 'update_directory', return_value=self.base / 'prepared'), \
             patch.object(updates, 'download_release', side_effect=download), \
             patch.object(updates, 'run_logged') as run:
            plan = updates.prepare_update(self.root, {'version': '1.1.0'}, self.folder)
        self.assertEqual(plan['environment'], str(self.folder))
        self.assertEqual(len(run.call_args_list), 1)
        self.assertEqual(run.call_args.args[0][-1], 'check')
        self.assertEqual(updates.installed_version(self.root), '1.0.0')
        self.assertFalse((self.root / updates.POINTER).exists())

    def test_source_zip_without_inventory_is_verified_against_its_original_release(self):
        (self.root / updates.MANIFEST).unlink()
        new_zip, old_zip = self.base / 'new.zip', self.base / 'old.zip'
        archive(new_zip, self.incoming)
        archive(old_zip, self.old, '1.0.0')
        def download(release, target):
            shutil.copyfile(old_zip if release['version'] == '1.0.0' else new_zip, target)
        with patch.object(updates, 'update_directory', return_value=self.base / 'prepared'), \
             patch.object(updates, 'download_release', side_effect=download), \
             patch.object(updates, 'fetch_json') as fetch, \
             patch.object(updates, 'release_info', return_value={'version': '1.0.0'}), \
             patch.object(updates, 'run_logged'):
            plan = updates.prepare_update(self.root, {'version': '1.1.0'}, self.folder)
        self.assertEqual(plan['baseline']['files'], self.baseline['files'])
        self.assertTrue(fetch.call_args.args[0].endswith('/tags/v1.0.0'))
        self.assertFalse((self.root / updates.MANIFEST).exists())

    def test_copied_git_folder_updates_without_git_and_keeps_history_and_settings(self):
        history = self.root / '.git/objects/example'
        history.parent.mkdir(parents=True)
        history.write_bytes(b'synthetic Git history - never replaced')
        personal = self.root / 'tensile_workbench.project.json'
        personal.write_bytes(b'{"synthetic": "personal settings"}')
        path = self.base / 'update.zip'
        archive(path, self.incoming)
        with patch.object(updates, 'find_git', return_value=None), \
             patch.object(updates, 'git', side_effect=AssertionError('Git must not run')), \
             patch.object(updates, 'update_directory', return_value=self.base / 'prepared'), \
             patch.object(updates, 'download_release', side_effect=lambda release, target: shutil.copyfile(path, target)), \
             patch.object(updates, 'run_logged'):
            plan = updates.prepare_update(self.root, {'version': '1.1.0'}, self.folder)
            self.assertFalse(plan['git'])
            updates.apply_update(plan)
            self.assertEqual(updates.installed_version(self.root), '1.1.0')
            self.assertEqual(json.loads((self.root / updates.MANIFEST).read_bytes())['update_method'], 'release')
            self.assertEqual(history.read_bytes(), b'synthetic Git history - never replaced')
            self.assertEqual(personal.read_bytes(), b'{"synthetic": "personal settings"}')
            # Installing Git later must not silently switch this copy's updater.
            newer = {**self.incoming, 'VERSION': b'1.2.0\n'}
            archive(path, newer, '1.2.0')
            with patch.object(updates, 'find_git', side_effect=AssertionError('Release mode needs no Git discovery')):
                next_plan = updates.prepare_update(self.root, {'version': '1.2.0'}, self.folder)
            self.assertFalse(next_plan['git'])
            updates.rollback_update(plan)
        self.assertEqual(updates.installed_version(self.root), '1.0.0')
        self.assertEqual(history.read_bytes(), b'synthetic Git history - never replaced')
        self.assertEqual(personal.read_bytes(), b'{"synthetic": "personal settings"}')

    def test_copied_checkout_without_inventory_verifies_release_without_git(self):
        (self.root / updates.MANIFEST).unlink()
        pointer = self.root / '.git'
        pointer.write_bytes(b'gitdir: /unavailable/original/checkout\n')
        new_zip, old_zip = self.base / 'new.zip', self.base / 'old.zip'
        archive(new_zip, self.incoming)
        archive(old_zip, self.old, '1.0.0')
        def download(release, target):
            shutil.copyfile(old_zip if release['version'] == '1.0.0' else new_zip, target)
        with patch.object(updates, 'find_git', return_value=None), \
             patch.object(updates, 'git', side_effect=AssertionError('Git must not run')), \
             patch.object(updates, 'update_directory', return_value=self.base / 'prepared'), \
             patch.object(updates, 'download_release', side_effect=download), \
             patch.object(updates, 'fetch_json'), \
             patch.object(updates, 'release_info', return_value={'version': '1.0.0'}), \
             patch.object(updates, 'run_logged'):
            plan = updates.prepare_update(self.root, {'version': '1.1.0'}, self.folder)
            updates.apply_update(plan)
        self.assertFalse(plan['git'])
        self.assertEqual(updates.installed_version(self.root), '1.1.0')
        self.assertEqual(pointer.read_bytes(), b'gitdir: /unavailable/original/checkout\n')

    def test_windows_line_endings_adopt_safely_but_code_edits_still_block(self):
        (self.root / '.git').mkdir()
        for name in ('app.py', 'requirements.txt'):
            target = self.root / name
            target.write_bytes(target.read_bytes().replace(b'\n', b'\r\n'))
        original = (self.root / 'app.py').read_bytes()
        path = self.base / 'update.zip'
        archive(path, self.incoming)
        with patch.object(updates, 'find_git', return_value=None), \
             patch.object(updates, 'git', side_effect=AssertionError('Git must not run')), \
             patch.object(updates, 'update_directory', return_value=self.base / 'prepared'), \
             patch.object(updates, 'download_release', side_effect=lambda release, target: shutil.copyfile(path, target)), \
             patch.object(updates, 'run_logged') as run:
            plan = updates.prepare_update(self.root, {'version': '1.1.0'}, self.folder)
            self.assertEqual(plan['environment'], str(self.folder))
            self.assertEqual(len(run.call_args_list), 1)  # No dependency reinstall for line endings.
            self.assertEqual(plan['baseline']['files']['app.py']['sha256'], updates.sha256(original))
            updates.apply_update(plan)
            updates.rollback_update(plan)
            self.assertEqual((self.root / 'app.py').read_bytes(), original)
            (self.root / 'app.py').write_bytes(original + b'# local edit\r\n')
            with self.assertRaisesRegex(updates.UpdateError, 'Local code has changed: app.py'):
                updates.prepare_update(self.root, {'version': '1.1.0'}, self.folder)
        self.assertEqual(updates.installed_version(self.root), '1.0.0')
        self.assertTrue((self.root / 'app.py').read_bytes().endswith(b'# local edit\r\n'))

    def test_reopening_update_window_clears_stale_shutdown_request(self):
        from unittest.mock import Mock
        with patch.object(update_bridge, 'update_directory', return_value=self.base / 'sessions'):
            bridge = update_bridge.UpdateBridge(self.root, self.folder)
        for name in ('request.json', 'stopped.json'):
            (bridge.directory / name).write_text('{}')
        with patch.object(update_bridge.subprocess, 'Popen', return_value=Mock()):
            bridge.open()
        self.assertFalse((bridge.directory / 'request.json').exists())
        self.assertFalse((bridge.directory / 'stopped.json').exists())

    def test_helper_failure_is_reported_once(self):
        from unittest.mock import Mock
        with patch.object(update_bridge, 'update_directory', return_value=self.base / 'sessions'):
            bridge = update_bridge.UpdateBridge(self.root, self.folder)
        bridge.helper = Mock()
        bridge.helper.poll.return_value = 1
        updates.write_json(bridge.directory / 'error.json', {'message': 'Tcl/Tk is unavailable.'})
        self.assertEqual(bridge.error(), 'Tcl/Tk is unavailable.')
        self.assertEqual(bridge.error(), '')

    def test_dependency_changes_build_separate_environment(self):
        path = self.base / 'dependencies.zip'
        self.incoming['requirements.txt'] = b'example>=2\n'
        archive(path, self.incoming)
        with patch.object(updates, 'update_directory', return_value=self.base / 'prepared'), \
             patch.object(updates, 'download_release', side_effect=lambda release, target: shutil.copyfile(path, target)), \
             patch.object(updates, 'run_logged') as run:
            plan = updates.prepare_update(self.root, {'version': '1.1.0'}, self.folder)
        self.assertNotEqual(plan['environment'], str(self.folder))
        self.assertEqual([call.args[0][-1] for call in run.call_args_list], ['setup', 'check'])
        self.assertFalse(self.folder.exists())

    def test_failed_dependency_preflight_never_switches_installation(self):
        path = self.base / 'dependencies.zip'
        archive(path, self.incoming)
        with patch.object(updates, 'update_directory', return_value=self.base / 'prepared'), \
             patch.object(updates, 'download_release', side_effect=lambda release, target: shutil.copyfile(path, target)), \
             patch.object(updates, 'run_logged', side_effect=updates.UpdateError('bad dependencies')):
            with self.assertRaisesRegex(updates.UpdateError, 'dependencies'):
                updates.prepare_update(self.root, {'version': '1.1.0'}, self.folder)
        self.assertEqual(updates.installed_version(self.root), '1.0.0')
        self.assertFalse((self.root / updates.POINTER).exists())

    def test_recovery_helper_is_kept_outside_replaced_source(self):
        (self.root / 'workbench_updates.py').write_text('# frozen code')
        with patch.object(update_workbench, 'update_directory', return_value=self.base / 'helpers'):
            helper = update_workbench.freeze_helper({'root': str(self.root)})
        update_workbench.recovery_launchers(self.plan, helper)
        self.assertFalse(helper.is_relative_to(self.root))
        self.assertEqual(helper.read_bytes(), self.old['tools/update_workbench.py'])
        self.assertTrue(list(self.directory.glob('Recover Tensile Workbench.*')))

    def test_other_server_prevents_update_without_exposing_its_token(self):
        secret = 'PRIVATE_TOKEN'
        command = f'python {self.root}/workbench_server.py --token={secret}'
        if sys.platform == 'win32':
            output = json.dumps([{'ProcessId': 123, 'CommandLine': command}])
        else:
            output = '123 ' + command
        with patch.object(updates.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output, '')):
            with self.assertRaises(updates.UpdateError) as failure:
                updates.assert_no_servers(self.root)
        self.assertNotIn(secret, str(failure.exception))

    def test_native_other_session_check_can_run(self):
        # Temporary fixture path cannot match the user's actual installation.
        updates.assert_no_servers(self.root)

    def test_dialog_installs_synthetic_release_through_real_button(self):
        try:
            import tkinter as tk
            window = tk.Tk()
            window.withdraw()
        except Exception as error:
            self.skipTest('Desktop Tk unavailable: ' + str(error))
        def close_window():
            try:
                window.destroy()
            except tk.TclError:
                pass
        self.addCleanup(close_window)
        session = self.base / 'session.json'
        updates.write_json(session, {'root': str(self.root), 'environment': str(self.folder),
                                    'nonce': 'ui-test', 'pid': os.getpid(), 'app': str(self.base / 'App.app')})
        (self.root / 'workbench_updates.py').write_text('# Synthetic frozen helper')
        clicked, timeout = [], []
        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)
        def click_ready():
            for child in children(window):
                try:
                    if child.cget('text') == 'Install update and restart' and not child.instate(['disabled']):
                        clicked.append(True)
                        child.invoke()
                        return
                except tk.TclError:
                    pass
            window.after(25, click_ready)
        def expire():
            timeout.append(True)
            window.destroy()
        window.after(25, click_ready)
        window.after(10000, expire)
        result = {'current': '1.0.0', 'available': True, 'release': {'version': '1.1.0', 'notes': 'Synthetic update'}}
        with patch.object(tk, 'Tk', return_value=window), \
             patch('tkinter.messagebox.askokcancel', return_value=True), \
             patch.object(update_workbench, 'update_directory', return_value=self.base / 'helpers'), \
             patch.object(update_workbench, 'check_release', return_value=result), \
             patch.object(update_workbench, 'prepare_update', return_value=self.plan), \
             patch.object(update_workbench, 'prepare_launcher'), \
             patch.object(update_workbench, 'wait_for_shutdown') as wait, \
             patch.object(update_workbench, 'assert_no_servers'), \
             patch.object(update_workbench, 'activate'), \
             patch.object(update_workbench, 'restart') as restart:
            update_workbench.show_dialog(session)
        self.assertTrue(clicked)
        self.assertFalse(timeout, 'The update window did not finish its button workflow.')
        wait.assert_called_once_with(session)
        restart.assert_called_once()
        self.assertEqual(updates.installed_version(self.root), '1.1.0')


class GitDiscoveryTests(unittest.TestCase):
    def test_existing_path_is_preferred(self):
        with patch.object(updates.shutil, 'which', return_value='/existing/git'):
            self.assertEqual(updates.find_git('win32', {}), '/existing/git')

    def test_optional_windows_git_locations_and_numeric_desktop_versions(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(updates.shutil, 'which', return_value=None):
            base = Path(temporary)
            local = base / 'Local App Data'
            older = local / 'GitHubDesktop/app-3.9.0/resources/app/git/cmd/git.exe'
            newer = local / 'GitHubDesktop/app-3.10.0/resources/app/git/cmd/git.exe'
            for path in (older, newer):
                path.parent.mkdir(parents=True)
                path.write_bytes(b'synthetic discovery fixture')
            (local / 'GitHubDesktop/app-3.11.0').mkdir()  # Incomplete bundle is skipped.
            env = {'LOCALAPPDATA': str(local), 'ProgramFiles': str(base / 'Program Files')}
            self.assertEqual(updates.find_git('win32', env), str(newer))
            normal = base / 'Program Files/Git/cmd/git.exe'
            normal.parent.mkdir(parents=True)
            normal.write_bytes(b'synthetic discovery fixture')
            self.assertEqual(updates.find_git('win32', env), str(normal))
            self.assertIsNone(updates.find_git('darwin', env))
            normal.unlink()
            older.unlink()
            newer.unlink()
            self.assertIsNone(updates.find_git('win32', env))


@unittest.skipUnless(shutil.which('git'), 'Git needed for checkout/update regression fixtures')
class GitUpdateTests(UpdateFixture):
    def setUp(self):
        super().setUp()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        updates.git(self.root, 'config', 'user.name', 'Synthetic Test')
        updates.git(self.root, 'config', 'user.email', 'test@example.invalid')
        updates.git(self.root, 'config', 'core.autocrlf', 'false')
        (self.root / '.gitignore').write_text('workbench-release.json\n.tensile-*\n*.project.json\n')
        updates.git(self.root, 'add', '.')
        updates.git(self.root, 'commit', '-qm', 'First synthetic release')

    def test_git_fast_forward_and_recovery_preserve_personal_files(self):
        baseline = updates.git_baseline(self.root)
        install(self.root, self.incoming, '1.1.0')
        (self.root / 'obsolete.py').unlink()
        updates.git(self.root, 'add', '.')
        updates.git(self.root, 'commit', '-qm', 'Next synthetic release')
        target = updates.git(self.root, 'rev-parse', 'HEAD')
        for name in ('.gitignore',):
            self.incoming[name] = (self.root / name).read_bytes()
        incoming = install(self.stage, self.incoming, '1.1.0')
        incoming['commit'] = target
        updates.git(self.root, 'reset', '--keep', baseline['commit'])
        personal = self.root / 'tensile_workbench.project.json'
        personal.write_text('personal')
        self.plan.update(baseline=baseline, incoming=incoming, git=True)
        self.apply()
        self.assertEqual(updates.git(self.root, 'rev-parse', 'HEAD'), target)
        self.assertEqual(personal.read_text(), 'personal')
        updates.rollback_update(self.plan)
        self.assertEqual(updates.git(self.root, 'rev-parse', 'HEAD'), baseline['commit'])
        self.assertEqual(personal.read_text(), 'personal')
        self.assertEqual(updates.git(self.root, 'status', '--porcelain', '--untracked-files=no'), '')

    def test_git_dirty_worktree_is_refused(self):
        (self.root / 'app.py').write_text('private changes')
        with self.assertRaisesRegex(updates.UpdateError, 'local code edits'):
            updates.git_baseline(self.root)

    def test_release_builder_uses_committed_files_and_excludes_ignored_data(self):
        (self.root / '.git/info/exclude').write_text('data/\n')
        (self.root / 'data').mkdir()
        (self.root / 'data/research.csv').write_bytes(b'not public')
        (self.root / 'app.py').write_bytes(b'not committed')
        path = build_release.build(self.root, self.base / 'release')
        with zipfile.ZipFile(path) as package:
            self.assertNotIn('data/research.csv', package.namelist())
            self.assertEqual(package.read('app.py'), self.old['app.py'])
        extracted = updates.unpack_release(path, self.base / 'built', '1.0.0')
        self.assertEqual(extracted['commit'], updates.git(self.root, 'rev-parse', 'HEAD'))


if __name__ == '__main__':
    unittest.main()
