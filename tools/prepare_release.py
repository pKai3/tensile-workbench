"""Prepare a numbered release of a verified main commit in a CI checkout.

Only VERSION and release notes change after verification. Branch/tag publication
is a separate atomic push, so a newer main commit cannot be overwritten.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workbench_updates import version


def prepare(root, expected):
    root = Path(root)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
    if git('status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Release preparation requires clean tracked files.')
    if git('rev-parse', 'HEAD') != expected:
        raise ValueError('The checkout is not the verified commit.')
    remote = git('rev-parse', 'origin/main')
    if remote != expected:
        # A rerun can finish publication after its version commit was pushed.
        # Only that exact metadata-only child is still covered by these checks.
        changes = set(git('diff', '--name-only', expected, remote).splitlines())
        if (git('rev-list', '--parents', '-n', '1', remote).split()[1:] != [expected]
                or not changes <= {'VERSION', 'RELEASE_NOTES.md'}
                or not re.fullmatch(r'Release v\d+\.\d+\.\d+', git('show', '-s', '--format=%s', remote))):
            return {'ready': 'false'}  # A newer push has its own verification run.
        git('checkout', '--detach', remote)
    head = git('rev-parse', 'HEAD')
    current = (root / 'VERSION').read_text().strip()
    current_number = version(current)
    tags = [tag for tag in git('tag', '--list').splitlines()
            if re.fullmatch(r'v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)', tag)]
    latest = max(tags, key=version) if tags else None
    tag = 'v' + current
    if tag in git('tag', '--points-at', head).splitlines():
        if latest != tag:
            raise ValueError('Refusing to republish a superseded version.')
        return {'ready': 'true', 'version': current, 'tag': tag, 'commit': head}
    previous = version(latest) if latest else None
    number = current_number if previous is None or current_number > previous else (*previous[:2], previous[2] + 1)
    current = '.'.join(map(str, number))
    tag = 'v' + current
    notes = (root / 'RELEASE_NOTES.md').read_text()
    old_notes = git('show', latest + ':RELEASE_NOTES.md') if latest else ''
    if not notes.strip() or notes.strip() == old_notes:
        subjects = git('log', '--reverse', '--format=%s', (latest + '..HEAD') if latest else 'HEAD').splitlines()
        subjects = [line for line in subjects if not re.fullmatch(r'Release v\d+\.\d+\.\d+', line)]
        body = '\n'.join('- ' + line for line in subjects)
        notes = '# Tensile Workbench ' + current + '\n\n' + body + '\n\nUse **Check for updates → Install update and restart**.\n'
    else:
        notes = re.sub(r'\A# [^\n]*', '# Tensile Workbench ' + current, notes)
    (root / 'VERSION').write_text(current + '\n')
    (root / 'RELEASE_NOTES.md').write_text(notes)
    git('add', 'VERSION', 'RELEASE_NOTES.md')
    if git('diff', '--cached', '--name-only'):
        git('commit', '-m', 'Release ' + tag)
    git('tag', tag)
    return {'ready': 'true', 'version': current, 'tag': tag, 'commit': git('rev-parse', 'HEAD')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected', required=True)
    args = parser.parse_args()
    result = prepare(ROOT, args.expected)
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        for key, value in result.items():
            output.write(f'{key}={value}\n')
    print(result)
