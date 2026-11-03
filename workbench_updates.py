"""Release downloads and recoverable code updates. Standard library only.

An update owns only manifest-listed source files. Research, settings, unknown
files, symlinks and the existing Python environment are never replacement targets.
The desktop helper stops its own server before calling apply_update.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid
import zipfile

REPOSITORY = 'pKai3/tensile-workbench'
API = 'https://api.github.com/repos/' + REPOSITORY
FORMAT = 'tensile-workbench-release-1'
MANIFEST = 'workbench-release.json'
POINTER = '.tensile-environment.json'
LOCK = '.tensile-update.lock'
MAX_DOWNLOAD = 128 * 1024 * 1024
MAX_CONTENTS = 512 * 1024 * 1024
PERSONAL = ('tensile_workbench.project.json', '.tensile-paths.json', POINTER)


class UpdateError(RuntimeError):
    pass


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def atomic_write(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, (json.dumps(value, indent=2) + '\n').encode('utf-8'))


def version(value):
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', str(value))
    if not match:
        raise UpdateError('The release must have a numbered version, such as 1.2.3.')
    return tuple(map(int, match.groups()))


def installed_version(root):
    value = (Path(root) / 'VERSION').read_text(encoding='utf-8').strip()
    version(value)
    return value


def update_directory(root):
    if sys.platform == 'darwin':
        base = Path.home() / 'Library/Application Support/Tensile Workbench'
    elif sys.platform == 'win32':
        base = Path(os.environ['LOCALAPPDATA']) / 'TensileWorkbench'
    else:  # Also permits isolated, platform-neutral regression fixtures.
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'tensile-workbench'
    key = sha256(os.path.normcase(str(Path(root).resolve())).encode())[:16]
    return base / 'updates' / key


def fetch_json(url):
    request = Request(url, headers={'Accept': 'application/vnd.github+json',
                                   'User-Agent': 'Tensile-Workbench-updater'})
    with urlopen(request, timeout=20) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise UpdateError('Release information is unexpectedly large.')
    return json.loads(raw)


def release_info(payload):
    tag = payload.get('tag_name', '')
    number = '.'.join(map(str, version(tag)))
    if payload.get('draft') or payload.get('prerelease'):
        raise UpdateError('Only published stable releases can be installed.')
    name = f'Tensile-Workbench-{number}.zip'
    matches = [a for a in payload.get('assets', []) if a.get('name') == name]
    if len(matches) != 1:
        raise UpdateError('This release does not have a Workbench update package yet.')
    asset = matches[0]
    url = asset.get('browser_download_url', '')
    expected = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}'
    digest = asset.get('digest', '') or ''
    if url != expected or not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest):
        raise UpdateError('The official release download or its SHA-256 digest is missing.')
    size = asset.get('size')
    if not isinstance(size, int) or not 0 < size <= MAX_DOWNLOAD:
        raise UpdateError('Unexpected update download size.')
    return {'version': number, 'tag': tag, 'url': url, 'sha256': digest[7:].lower(),
            'size': size, 'notes': str(payload.get('body') or 'No release notes supplied.'),
            'page': f'https://github.com/{REPOSITORY}/releases/tag/{tag}'}


def check_release(root):
    current = installed_version(root)
    try:
        release = release_info(fetch_json(API + '/releases/latest'))
    except HTTPError as error:
        if error.code == 404:
            return {'current': current, 'available': False, 'message': 'No published updates yet.'}
        raise UpdateError('Could not check GitHub for updates. Try again later.') from error
    return {'current': current, 'available': version(release['version']) > version(current),
            'release': release, 'message': 'You are up to date.'}


def download_release(release, path):
    request = Request(release['url'], headers={'User-Agent': 'Tensile-Workbench-updater'})
    digest, total = hashlib.sha256(), 0
    try:
        with urlopen(request, timeout=30) as response, Path(path).open('xb') as output:
            if urlsplit(response.url).scheme != 'https':
                raise UpdateError('The release download did not stay on HTTPS.')
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_DOWNLOAD or total > release['size']:
                    raise UpdateError('The download is larger than the published package.')
                digest.update(chunk)
                output.write(chunk)
        if total != release['size'] or digest.hexdigest() != release['sha256']:
            raise UpdateError('The update download is incomplete or its checksum does not match.')
    except BaseException:
        Path(path).unlink(missing_ok=True)
        raise


def safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise UpdateError('Unsafe path in update package.')
    parts = name.split('/')
    if any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in parts):
        raise UpdateError('Unsafe path in update package: ' + name)
    if any(re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', p) for p in parts):
        raise UpdateError('Reserved filename in update package: ' + name)
    return name


def managed_name(name):
    safe_name(name)
    first = name.split('/')[0].casefold()
    if (first in {'.git', 'data', 'output', 'outputs', 'archive', 'share', 'venv'}
            or first.startswith(('.venv', '.tensile-', '.env'))
            or first.startswith('tensile_workbench') and '.project.' in first
            or name == MANIFEST):
        raise UpdateError('An update cannot manage personal files: ' + name)
    return name


def validate_manifest(value):
    if not isinstance(value, dict) or value.get('format') != FORMAT:
        raise UpdateError('Unrecognised update package.')
    version(value.get('version'))
    if value.get('python') != '3.14' or not re.fullmatch(r'[a-f0-9]{40}', value.get('commit', '')):
        raise UpdateError('This update requires a different runtime or has no source revision. Use the new installer.')
    if value.get('update_method') not in (None, 'release', 'git'):
        raise UpdateError('Unrecognised installed update method.')
    files = value.get('files')
    if not isinstance(files, dict) or not files or len(files) > 5000:
        raise UpdateError('Invalid release file list.')
    seen = set()
    for name, entry in files.items():
        managed_name(name)
        folded = name.casefold()
        if folded in seen or not isinstance(entry, dict):
            raise UpdateError('Duplicate release path.')
        seen.add(folded)
        if not re.fullmatch(r'[a-f0-9]{64}', entry.get('sha256', '')) or entry.get('mode') not in (0o644, 0o755):
            raise UpdateError('Invalid release file checksum or permissions.')
    if not {'VERSION', 'workbench_environment.py', 'requirements.txt', 'tools/update_workbench.py'} <= files.keys():
        raise UpdateError('The update package is incomplete.')
    return value


def unpack_release(archive, destination, expected_version):
    """Validate the entire archive before writing; never use extractall."""
    destination = Path(destination)
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) > 5001 or sum(i.file_size for i in entries) > MAX_CONTENTS:
            raise UpdateError('The unpacked update is unexpectedly large.')
        seen = set()
        for entry in entries:
            safe_name(entry.filename)
            if (entry.filename.casefold() in seen or entry.is_dir()
                    or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)):
                raise UpdateError('Duplicate, linked or unsupported file in update package.')
            seen.add(entry.filename.casefold())
        manifest = validate_manifest(json.loads(package.read(MANIFEST)))
        if manifest['version'] != expected_version:
            raise UpdateError('The package version does not match the selected release.')
        if {i.filename for i in entries} != set(manifest['files']) | {MANIFEST}:
            raise UpdateError('The package contents do not match its file list.')
        for name, entry in manifest['files'].items():
            raw = package.read(name)
            if sha256(raw) != entry['sha256']:
                raise UpdateError('File checksum failed: ' + name)
        if package.read('VERSION').decode('utf-8').strip() != expected_version:
            raise UpdateError('VERSION does not match the release.')
        destination.mkdir(parents=True, exist_ok=False)
        for name, entry in manifest['files'].items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.read(name))
            target.chmod(entry['mode'])
        (destination / MANIFEST).write_bytes(package.read(MANIFEST))
    return manifest


def local_path(root, name):
    """Reject linked parents, including directory junctions on Windows."""
    safe_name(name)
    path = Path(root)
    for part in PurePosixPath(name).parts:
        path = path / part
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise UpdateError('An update cannot replace a linked path: ' + name)
    if path.exists() and not path.is_file():
        raise UpdateError('A folder occupies a release file path: ' + name)
    return path


def find_git(system=None, environ=None):
    """Find Git without requiring a Windows desktop app to inherit a fresh PATH."""
    system = sys.platform if system is None else system
    environ = os.environ if environ is None else environ
    found = shutil.which('git', path=environ.get('PATH', os.defpath))
    if found:
        return found
    if system == 'win32':
        candidates = []
        for key in ('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)'):
            if environ.get(key):
                candidates.append(Path(environ[key]) / 'Git/cmd/git.exe')
        if environ.get('LOCALAPPDATA'):
            local = Path(environ['LOCALAPPDATA'])
            candidates.append(local / 'Programs/Git/cmd/git.exe')
            desktop = local / 'GitHubDesktop'
            # Desktop keeps versioned bundles; 3.10 must sort after 3.9.
            bundles = [path for path in desktop.glob('app-*')
                       if re.fullmatch(r'app-\d+(?:\.\d+)+', path.name)]
            bundles.sort(key=lambda path: tuple(map(int, path.name[4:].split('.'))), reverse=True)
            candidates.extend(path / 'resources/app/git/cmd/git.exe' for path in bundles)
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return None


def missing_git_message():
    return ('Git became unavailable during this checkout update. Close and reopen the '
            'update window to retry using the release package. Git history will be kept; '
            'installing Git is not required.')


def git(root, *args):
    executable = find_git()
    if executable is None:
        raise UpdateError(missing_git_message())
    try:
        result = subprocess.run([executable, '-C', str(root), *args], check=True,
                                capture_output=True, text=True, encoding='utf-8', timeout=120,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                                env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
        return result.stdout.strip()
    except FileNotFoundError as error:
        raise UpdateError(missing_git_message()) from error
    except (OSError, subprocess.SubprocessError) as error:
        detail = getattr(error, 'stderr', '') or str(error)
        raise UpdateError('Git could not safely update this checkout. ' + detail.strip()) from error


def git_baseline(root):
    if git(root, 'status', '--porcelain', '--untracked-files=no'):
        raise UpdateError('This Git checkout has local code edits. Commit or set them aside before updating. Saved settings are unaffected.')
    if Path(git(root, 'rev-parse', '--show-toplevel')).resolve() != Path(root).resolve():
        raise UpdateError('The workbench must be the root of its own Git checkout.')
    files = {}
    for row in git(root, 'ls-files', '-s').splitlines():
        metadata, name = row.split('\t', 1)
        mode, _, stage = metadata.split()
        managed_name(name)
        if mode not in ('100644', '100755') or stage != '0':
            raise UpdateError('Linked or unresolved Git files prevent updating.')
        path = local_path(root, name)
        files[name] = {'sha256': sha256(path.read_bytes()), 'mode': int(mode[-3:], 8)}
    return {'files': files, 'commit': git(root, 'rev-parse', 'HEAD'),
            'branch': git(root, 'symbolic-ref', '--short', 'HEAD')}


def validate_baseline(root, baseline, incoming):
    for name, entry in baseline['files'].items():
        path = local_path(root, name)
        if not path.is_file() or sha256(path.read_bytes()) != entry['sha256']:
            raise UpdateError('Local code has changed: ' + name + '. Keep a copy and resolve these edits before updating.')
    for name in incoming['files'].keys() - baseline['files'].keys():
        path = local_path(root, name)
        if path.exists():
            raise UpdateError('A local file occupies a new release path: ' + name + '. It was not overwritten.')


def release_baseline(root, baseline):
    """Recognise Windows text checkout endings, retaining exact local backup hashes.

    Only CRLF-to-LF equivalence with a verified release is accepted. Changes to
    code, missing files and linked paths still fail the normal baseline check.
    """
    files = {name: dict(entry) for name, entry in baseline['files'].items()}
    for name, entry in files.items():
        path = local_path(root, name)
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if sha256(raw) != entry['sha256'] and b'\r\n' in raw and b'\0' not in raw:
            try:
                raw.decode('utf-8')
            except UnicodeDecodeError:
                continue
            if sha256(raw.replace(b'\r\n', b'\n')) == entry['sha256']:
                entry['sha256'] = sha256(raw)
    return {**baseline, 'files': files}


def prepare_update(root, release, folder, progress=lambda text: None):
    """Download/validate first, while the old app remains usable. No code writes."""
    root, folder = Path(root).resolve(), Path(folder).resolve()
    if (root / LOCK).exists():
        raise UpdateError('A previous update needs recovery. Restore it before updating again.')
    installed = (validate_manifest(json.loads((root / MANIFEST).read_bytes()))
                 if (root / MANIFEST).is_file() else None)
    # A copied .git folder must not impose a Git installation on end users.
    # Once adopted, release updates stay independent of later PATH/Git changes.
    is_git = ((root / '.git').exists() and (installed or {}).get('update_method') != 'release'
              and find_git() is not None)
    baseline = git_baseline(root) if is_git else installed
    progress('Downloading and verifying the update…')
    directory = update_directory(root) / (release['version'] + '-' + uuid.uuid4().hex[:10])
    directory.mkdir(parents=True, mode=0o700)
    archive = directory / 'release.zip'
    download_release(release, archive)
    stage = directory / 'source'
    incoming = unpack_release(archive, stage, release['version'])
    if is_git:
        progress('Checking that the release safely advances this Git checkout…')
        git(root, 'fetch', '--no-tags', 'https://github.com/' + REPOSITORY + '.git',
            'refs/tags/' + release['tag'])
        target = git(root, 'rev-parse', 'FETCH_HEAD^{commit}')
        if target != incoming['commit']:
            raise UpdateError('The release package does not match its Git tag.')
        git(root, 'merge-base', '--is-ancestor', baseline['commit'], target)
    elif baseline is None:
        # A GitHub source ZIP has no generated inventory. Verify its existing
        # files against its own official release before adopting that inventory.
        progress('Verifying this installation against its original release…')
        current = installed_version(root)
        previous = release_info(fetch_json(API + '/releases/tags/v' + current))
        download_release(previous, directory / 'previous.zip')
        baseline = unpack_release(directory / 'previous.zip', directory / 'previous-source', current)
    if not is_git:
        baseline = release_baseline(root, baseline)
    validate_baseline(root, baseline, incoming)
    progress('Checking the updated app and its dependencies…')
    from workbench_environment import child_environment, python_in, validate_environment_location
    candidate = folder
    if (root / 'requirements.txt').read_text(encoding='utf-8') != (stage / 'requirements.txt').read_text(encoding='utf-8'):
        candidate = directory / 'runtime' / 'venv'
        validate_environment_location(candidate, root)
        progress('Preparing new dependencies; the current environment is being kept…')
        env = child_environment(candidate)
        env['TENSILE_ENV_DIR'] = str(candidate)
        run_logged([sys.executable, stage / 'workbench_environment.py', 'setup'], directory, env)
    # Check personal definitions without writing/migrating the live settings.
    for name in PERSONAL[:2]:
        if (root / name).is_file():
            shutil.copyfile(root / name, stage / name)
    env = child_environment(candidate)
    env['TENSILE_ENV_DIR'] = str(candidate)
    run_logged([python_in(candidate, sys.platform), stage / 'workbench_environment.py', 'check'], directory, env)
    plan = {'root': str(root), 'directory': str(directory), 'stage': str(stage),
            'baseline': baseline, 'incoming': incoming, 'git': is_git,
            'environment': str(candidate), 'previous_environment': str(folder), 'state': 'prepared'}
    write_json(directory / 'transaction.json', plan)
    return plan


def run_logged(command, directory, env=None):
    with (Path(directory) / 'update.log').open('a', encoding='utf-8') as log:
        result = subprocess.run([str(x) for x in command], stdout=log, stderr=log,
                                cwd=directory, env=env, timeout=1200,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise UpdateError('The update check failed. The existing installation is kept. See ' + str(Path(directory) / 'update.log'))


def backup_file(root, name, backup):
    path = local_path(root, name)
    if not path.exists():
        return None
    target = Path(backup) / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return {'sha256': sha256(path.read_bytes()), 'mode': stat.S_IMODE(path.stat().st_mode)}


def update_state(plan, state):
    plan['state'] = state
    write_json(Path(plan['directory']) / 'transaction.json', plan)


def apply_update(plan, activate=lambda plan: None, restore_launcher=lambda plan: None):
    """Called only after the launcher has acknowledged shutdown and exited."""
    root, directory = Path(plan['root']), Path(plan['directory'])
    validate_baseline(root, plan['baseline'], plan['incoming'])
    if plan['git'] and git_baseline(root)['commit'] != plan['baseline']['commit']:
        raise UpdateError('The checkout changed while the update was preparing. Try again.')
    if plan['git'] and git(root, 'symbolic-ref', '--short', 'HEAD') != plan['baseline']['branch']:
        raise UpdateError('The Git branch changed while the update was preparing. Try again.')
    lock = root / LOCK
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump({'pid': os.getpid(), 'transaction': str(directory / 'transaction.json')}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        backup = directory / 'backup'
        names = sorted(set(plan['baseline']['files']) | set(plan['incoming']['files']) | {MANIFEST, POINTER})
        plan['backup'] = {name: backup_file(root, name, backup) for name in names}
        # A separately retained, byte-for-byte settings snapshot. Code rollback
        # does not overwrite settings subsequently changed by the user.
        for name in PERSONAL[:2]:
            backup_file(root, name, directory / 'saved-settings')
        update_state(plan, 'applying')  # Durable journal precedes all code writes.
        if plan['git']:
            (directory / 'no-hooks').mkdir(exist_ok=True)
            git(root, '-c', 'core.hooksPath=' + str(directory / 'no-hooks'), 'merge', '--ff-only', plan['incoming']['commit'])
        else:
            for name, entry in plan['incoming']['files'].items():
                target = local_path(root, name)
                atomic_write(target, (Path(plan['stage']) / name).read_bytes())
                target.chmod(entry['mode'])
            for name in plan['baseline']['files'].keys() - plan['incoming']['files'].keys():
                local_path(root, name).unlink()
        write_json(root / MANIFEST, {**plan['incoming'], 'update_method': 'git' if plan['git'] else 'release'})
        write_json(root / POINTER, {'schema_version': 1, 'environment': plan['environment']})
        update_state(plan, 'activating')
        activate(plan)
        update_state(plan, 'complete')
        lock.unlink()
    except BaseException:
        if plan.get('state') in ('applying', 'activating'):
            rollback_update(plan, restore_launcher)
        else:
            lock.unlink(missing_ok=True)
        raise


def assert_no_servers(root):
    """Refuse replacement while another launcher/notebook uses this checkout.

    Inspect command lines internally only; never print tokens from them. The
    controlling launcher's acknowledgement remains mandatory independently.
    """
    if sys.platform == 'win32':
        query = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                 '[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding; '
                 'Get-CimInstance Win32_Process | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress']
    else:
        query = ['/bin/ps', '-axo', 'pid=,command=']
    try:
        result = subprocess.run(query, check=True, capture_output=True, text=True, encoding='utf-8', timeout=15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if sys.platform == 'win32':
            rows = json.loads(result.stdout)
            rows = rows if isinstance(rows, list) else [rows]
            commands = [(row.get('ProcessId'), row.get('CommandLine') or '') for row in rows]
        else:
            commands = [(int(row.strip().split(None, 1)[0]), row.strip().split(None, 1)[1])
                        for row in result.stdout.splitlines() if len(row.strip().split(None, 1)) == 2]
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise UpdateError('Could not verify that other Workbench sessions have stopped. No files were replaced.') from error
    identity = str(Path(root).resolve()).replace('\\', '/').casefold()
    for pid, command in commands:
        command = command.replace('\\', '/').casefold()
        if pid != os.getpid() and identity in command and any(
                name in command for name in ('workbench_server.py', 'windows_server.py', 'jupyterlab', 'ipykernel_launcher')):
            raise UpdateError('Another Workbench server or notebook is using this folder. Close it before updating. No files were replaced.')


def rollback_update(plan, restore_launcher=lambda plan: None):
    root, directory = Path(plan['root']), Path(plan['directory'])
    if plan.get('state') == 'prepared':
        # A crash during snapshot creation precedes the durable "applying"
        # journal, so no application files have been replaced yet.
        validate_baseline(root, plan['baseline'], plan['incoming'])
        update_state(plan, 'rolled-back')
        (root / LOCK).unlink(missing_ok=True)
        return
    if not plan.get('backup'):
        raise UpdateError('The update backup is incomplete; no files were restored.')
    # Validate ALL backups before touching current files.
    for name, entry in plan['backup'].items():
        local_path(root, name)
        if entry and sha256((directory / 'backup' / name).read_bytes()) != entry['sha256']:
            raise UpdateError('A recovery checksum failed: ' + name)
        if not plan['git'] and name not in (MANIFEST, POINTER):
            path = local_path(root, name)
            current = sha256(path.read_bytes()) if path.is_file() else None
            old = entry['sha256'] if entry else None
            new = plan['incoming']['files'].get(name, {}).get('sha256')
            if current not in (old, new):
                raise UpdateError('Code was edited after the update: ' + name + '. Recovery will not overwrite those edits.')
    if plan['git']:
        head = git(root, 'rev-parse', 'HEAD')
        if git(root, 'symbolic-ref', '--short', 'HEAD') != plan['baseline']['branch']:
            raise UpdateError('The Git branch changed after this update. Recovery will not change another branch.')
        if head not in (plan['baseline']['commit'], plan['incoming']['commit']):
            raise UpdateError('Git has changed since this update; automatic recovery would overwrite later work.')
        # --keep refuses intervening local changes. Never use reset --hard.
        if head != plan['baseline']['commit']:
            (directory / 'no-hooks').mkdir(exist_ok=True)
            git(root, '-c', 'core.hooksPath=' + str(directory / 'no-hooks'), 'reset', '--keep', plan['baseline']['commit'])
    for name, entry in plan['backup'].items():
        if plan['git'] and name not in (MANIFEST, POINTER):
            continue
        path = local_path(root, name)
        if entry is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, (directory / 'backup' / name).read_bytes())
            path.chmod(entry['mode'])
    restore_launcher(plan)
    update_state(plan, 'rolled-back')
    (root / LOCK).unlink(missing_ok=True)


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied is not proof of exit.
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def wait_for_shutdown(session, timeout=90):
    session = Path(session)
    metadata = json.loads(session.read_bytes())
    write_json(session.with_name('request.json'), {'nonce': metadata['nonce'], 'action': 'stop-for-update'})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ack = session.with_name('stopped.json')
        if ack.is_file() and json.loads(ack.read_bytes()).get('nonce') == metadata['nonce']:
            if not process_alive(metadata['pid']):
                return
        time.sleep(.25)
    session.with_name('request.json').unlink(missing_ok=True)
    raise UpdateError('The launcher did not finish stopping. No code was replaced. Close other Workbench sessions and try again.')
