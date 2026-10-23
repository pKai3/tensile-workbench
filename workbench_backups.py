"""Small, local, checksummed settings snapshots, separate from the checkout.

Only the two named settings files are managed. No research data is copied.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import base64
import hashlib
import json
import os
import sys
import tempfile
import uuid

PROJECT_NAME = 'tensile_workbench.project.json'
PATHS_NAME = '.tensile-paths.json'
FORMAT = 'tensile-workbench-backup-1'
PROTECTED = {'manual', 'pre-migration', 'pre-restore'}
_warnings = {}


class ProjectConflict(RuntimeError):
    pass


class RecoveryRequired(ValueError):
    """An existing installation must not be silently reset to defaults."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def read_optional(path):
    try:
        return Path(path).read_bytes()
    except FileNotFoundError:
        return None


def atomic_bytes(path, content):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        # Best-effort directory durability. Once replace has committed, never
        # report a failed save (and leave the caller holding the old revision).
        if os.name != 'nt':
            try:
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except OSError:
                pass  # Some network/cloud filesystems do not support this.
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


@contextmanager
def settings_lock(path):
    lock = Path(path).with_suffix('.lock')
    token = f'{os.getpid()} {uuid.uuid4().hex}'
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ProjectConflict('Settings are being saved by another session. Try again. '
                              f'If a crashed session left a stale lock, close all sessions before removing {lock}.') from error
    try:
        with os.fdopen(handle, 'w') as stream:
            stream.write(token)
        yield
    finally:
        # Never remove a replacement lock created by another process.
        if read_optional(lock) == token.encode():
            lock.unlink()


def default_backup_root():
    custom = os.environ.get('TENSILE_WORKBENCH_BACKUP_DIR')
    if custom:
        return Path(custom).expanduser().resolve()
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/Tensile Workbench/backups'
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Tensile Workbench/backups'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'tensile-workbench/backups'


def backup_warning(path):
    return _warnings.get(str(Path(path).resolve()), '')


def validate_paths(raw):
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get('schema_version') != 1:
        raise ValueError('Unrecognised folder-settings version.')
    for key in ('data_directory', 'output_directory'):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError('Saved folder settings are incomplete.')
    if 'show_sample_data' in value and not isinstance(value['show_sample_data'], bool):
        raise ValueError('Invalid sample-data visibility preference.')
    if 'sample_data_directory' in value and (not isinstance(value['sample_data_directory'], str)
                                             or not value['sample_data_directory'].strip()):
        raise ValueError('Invalid sample-data folder.')
    return value


def validate_settings(path, raw):
    if Path(path).name == PATHS_NAME:
        return validate_paths(raw)
    from workbench_project import decode_project
    return decode_project(raw)


def recovery_problem(path):
    """Read-only startup guard, usable before constructing the workbench."""
    path = Path(path)
    try:
        raw = read_optional(path)
        if raw is None:
            if BackupVault(path).has_history() or path.with_suffix('.previous.json').exists():
                return f'{path.name} is missing, but saved history exists. Use Backups & restore; defaults were not written.'
            return ''
        validate_settings(path, raw)
    except Exception as error:
        return f'Cannot read {path.name}: {error}. The file has been preserved. Use Backups & restore.'
    return ''


class BackupVault:
    """20 recent snapshots + 30 daily checkpoints; protected snapshots persist."""
    def __init__(self, path, root=None):
        self.path = Path(path).expanduser().resolve()
        key = hashlib.sha256(str(self.path.parent).encode()).hexdigest()[:20]
        self.directory = Path(root or default_backup_root()) / key / self.path.name
        self._last_hash = None

    def has_history(self):
        return self.directory.exists() and any(self.directory.glob('*.json'))

    def read(self, path):
        path = Path(path)
        if path.parent.resolve() != self.directory.resolve() or path.suffix != '.json':
            raise ValueError('Choose a snapshot from this installation’s backup list.')
        document = json.loads(path.read_bytes())
        if not isinstance(document, dict) or document.get('format') != FORMAT or document.get('source') != str(self.path):
            raise ValueError('Snapshot belongs to a different settings file.')
        if not isinstance(document.get('reason'), str) or not document['reason']:
            raise ValueError('Snapshot metadata is incomplete.')
        raw = base64.b64decode(document['content'], validate=True)
        if digest(raw) != document['sha256']:
            raise ValueError('Snapshot checksum failed; this backup is damaged.')
        datetime.fromisoformat(document['created'])
        return document, raw

    def entries(self):
        entries = []
        for path in sorted(self.directory.glob('*.json'), reverse=True):
            try:
                document, raw = self.read(path)
                project = validate_settings(self.path, raw)
                entries.append({**document, 'path': path, 'valid': True,
                                'graphs': len(project.get('graphs', [])) if self.path.name != PATHS_NAME else None,
                                'revision': project.get('revision')})
            except Exception as error:
                entries.append({'path': path, 'valid': False, 'error': str(error)})
        return entries

    def capture(self, raw, *, reason='autosave', force=False, now=None):
        if raw is None:
            return None
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        checksum = digest(raw)
        # Do not churn snapshots for a reload or unchanged save on the same day.
        signature = (checksum, now.date())
        if not force and self._last_hash == signature:
            return None
        if not force:
            newest = next(iter(sorted(self.directory.glob('*.json'), reverse=True)), None)
            if newest is not None:
                try:
                    previous, _ = self.read(newest)
                    if previous['sha256'] == checksum and datetime.fromisoformat(previous['created']).date() == now.date():
                        self._last_hash = signature
                        return newest
                except (ValueError, KeyError):
                    pass  # Preserve damaged snapshots; make a new verified one.
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = now.strftime('%Y%m%dT%H%M%S.%fZ') + '-' + uuid.uuid4().hex[:12] + '.json'
        target = self.directory / name
        document = dict(format=FORMAT, source=str(self.path), created=now.isoformat(),
                        reason=reason, sha256=checksum, content=base64.b64encode(raw).decode('ascii'))
        atomic_bytes(target, (json.dumps(document, indent=2) + '\n').encode())
        if self.read(target)[1] != raw:
            raise OSError('Backup read-back verification failed.')
        self._prune()
        self._last_hash = signature
        return target

    def _prune(self):
        entries = []
        for path in sorted(self.directory.glob('*.json'), reverse=True):
            try:
                document, raw = self.read(path)
                entries.append((path, document))
            except Exception:
                continue
        # Protected originals (including corrupt pre-restore copies) must not
        # displace the regular recent versions or daily recovery checkpoints.
        automatic = [(path, document) for path, document in entries if document['reason'] not in PROTECTED]
        keep = {path for path, _ in automatic[:20]}
        keep.update(path for path, document in entries if document['reason'] in PROTECTED)
        days = set()
        for path, document in automatic:
            day = datetime.fromisoformat(document['created']).date()
            if day not in days and len(days) < 30:
                days.add(day)
                keep.add(path)
        for path, _ in entries:
            if path not in keep:
                try:
                    # Validate only deletion candidates, not the whole history
                    # on every keystroke save. Damaged originals are preserved.
                    _, raw = self.read(path)
                    validate_settings(self.path, raw)
                except Exception:
                    continue
                path.unlink()  # Exact validated file in our dedicated vault only.

    def try_capture(self, raw, *, reason='autosave'):
        try:
            self.capture(raw, reason=reason, force=reason in PROTECTED)
            _warnings.pop(str(self.path), None)
        except Exception as error:
            _warnings[str(self.path)] = f'Automatic backup failed: {error}'
        return backup_warning(self.path)

    def restore(self, snapshot, *, expected_current, expected_snapshot):
        """Restore only after confirmation; refuse intervening edits or tampering."""
        snapshot = Path(snapshot)
        if snapshot == self.path.with_suffix('.previous.json'):
            raw = snapshot.read_bytes()
        else:
            _, raw = self.read(snapshot)
        if digest(raw) != expected_snapshot:
            raise ProjectConflict('The selected backup changed. Refresh and review it again.')
        validate_settings(self.path, raw)
        with settings_lock(self.path):
            current = read_optional(self.path)
            if digest(current) != expected_current:
                raise ProjectConflict('Settings changed after you selected Restore. Refresh and review again.')
            # Mandatory, including damaged originals. Never overwrite first and
            # hope a safety copy succeeds afterwards.
            self.capture(current, reason='pre-restore', force=True)
            atomic_bytes(self.path, raw)
            self.try_capture(raw, reason='restored')
        return raw
