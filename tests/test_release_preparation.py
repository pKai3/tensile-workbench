"""Automatic releases must preserve verified code and concurrent work."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.prepare_release import prepare
from tools.build_release import build
from workbench_updates import unpack_release


@unittest.skipUnless(shutil.which('git'), 'Git needed for synthetic release repositories')
class ReleasePreparationTests(unittest.TestCase):
    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True).strip()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tw-release-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'checkout'
        self.root.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Synthetic Release Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'core.autocrlf', 'false')
        for name, text in {'VERSION': '1.0.2\n', 'RELEASE_NOTES.md': '# Tensile Workbench 1.0.2\n\nOld notes\n',
                           '.gitignore': 'data/\n', 'app.py': '# original\n', 'requirements.txt': '',
                           'workbench_environment.py': '', 'tools/update_workbench.py': ''}.items():
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(text)
        self.git('add', '.')
        self.git('commit', '-qm', 'Initial synthetic version')
        self.git('tag', 'v1.0.2')
        subprocess.run(['git', 'init', '--bare', '-q', str(self.base / 'origin')], check=True)
        self.git('remote', 'add', 'origin', str(self.base / 'origin'))
        (self.root / 'app.py').write_text('# verified change\n')
        self.git('commit', '-qam', 'Improve synthetic preview')
        self.git('push', '-q', 'origin', 'main', '--tags')
        self.source = self.git('rev-parse', 'HEAD')

    def test_patch_release_preserves_code_and_packages_matching_version(self):
        (self.root / 'data').mkdir()
        (self.root / 'data/private.csv').write_text('private')
        result = prepare(self.root, self.source)
        self.assertEqual(result['version'], '1.0.3')
        self.assertEqual(set(self.git('diff', '--name-only', self.source, 'HEAD').splitlines()),
                         {'VERSION', 'RELEASE_NOTES.md'})
        self.assertIn('Improve synthetic preview', (self.root / 'RELEASE_NOTES.md').read_text())
        archive = build(self.root, self.base / 'dist')
        manifest = unpack_release(archive, self.base / 'unpacked', '1.0.3')
        self.assertEqual(manifest['commit'], result['commit'])
        self.assertNotIn('data/private.csv', manifest['files'])

    def test_explicit_larger_version_and_curated_notes_are_preserved(self):
        (self.root / 'VERSION').write_text('1.1.0\n')
        (self.root / 'RELEASE_NOTES.md').write_text('# Next release\n\n- User-facing explanation.\n')
        self.git('commit', '-qam', 'Prepare feature release')
        self.git('push', '-q', 'origin', 'main')
        result = prepare(self.root, self.git('rev-parse', 'HEAD'))
        self.assertEqual(result['version'], '1.1.0')
        self.assertEqual((self.root / 'RELEASE_NOTES.md').read_text(),
                         '# Tensile Workbench 1.1.0\n\n- User-facing explanation.\n')

    def test_numeric_order_uses_next_patch_after_highest_tag(self):
        self.git('tag', 'v1.0.9')
        self.git('tag', 'v1.0.10')
        self.git('tag', 'v9.0.0-rc1')
        self.assertEqual(prepare(self.root, self.source)['version'], '1.0.11')

    def test_prepared_manual_version_can_tag_the_already_verified_commit(self):
        (self.root / 'VERSION').write_text('1.2.0\n')
        (self.root / 'RELEASE_NOTES.md').write_text('# Tensile Workbench 1.2.0\n\n- Ready.\n')
        self.git('commit', '-qam', 'Prepare release')
        self.git('push', '-q', 'origin', 'main')
        source = self.git('rev-parse', 'HEAD')
        self.assertEqual(prepare(self.root, source)['commit'], source)

    def test_newer_code_push_skips_stale_verified_commit(self):
        (self.root / 'app.py').write_text('# later change\n')
        self.git('commit', '-qam', 'Later work')
        self.git('push', '-q', 'origin', 'main')
        self.git('checkout', '-q', '--detach', self.source)
        self.assertEqual(prepare(self.root, self.source), {'ready': 'false'})
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.source)
        self.assertNotIn('v1.0.3', self.git('tag', '--list'))

    def test_retry_after_version_push_reuses_exact_tag_without_another_bump(self):
        first = prepare(self.root, self.source)
        self.git('push', '-q', '--atomic', 'origin', 'HEAD:refs/heads/main', 'refs/tags/v1.0.3')
        self.git('checkout', '-q', '--detach', self.source)
        self.assertEqual(prepare(self.root, self.source), first)
        self.assertEqual(prepare(self.root, first['commit']), first)

    def test_dirty_files_or_wrong_checked_commit_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'verified commit'):
            prepare(self.root, '0' * 40)
        (self.root / 'app.py').write_text('# unverified change\n')
        with self.assertRaisesRegex(ValueError, 'clean tracked'):
            prepare(self.root, self.source)
