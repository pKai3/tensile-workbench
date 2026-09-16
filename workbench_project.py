"""Versioned project definitions with atomic autosave and conflict protection."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import re
import tempfile
import uuid


class ProjectConflict(RuntimeError):
    pass


def validate_project(project):
    if project.get('schema_version') != 1:
        raise ValueError('Unsupported workbench project schema; the existing file was not changed.')
    graphs = project.get('graphs', [])
    if not graphs:
        raise ValueError('A project needs at least one graph definition.')
    ids, names = set(), set()
    for graph in graphs:
        ident = graph['id']
        name = graph['name'].strip()
        if not ident or ident in ids or not name or name.casefold() in names:
            raise ValueError('Graph names and IDs must be nonempty and unique.')
        ids.add(ident)
        names.add(name.casefold())
        if not isinstance(graph.get('settings'), dict) or not isinstance(graph.get('definition'), dict):
            raise ValueError('Each graph needs calculation settings and a definition.')
        if not isinstance(graph['settings'].get('groups'), list):
            raise ValueError('Graph sample groups must be a list.')
        if len(set(graph['settings']['groups'])) != len(graph['settings']['groups']):
            raise ValueError('Sample groups cannot be repeated.')
        if not isinstance(graph['settings'].get('families'), list):
            raise ValueError('Visible plot types must be a list.')
        for group, color in graph['definition'].get('color_overrides', {}).items():
            if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                raise ValueError(f'Colour override for {group} must be a six-digit hex colour, e.g. #1f77b4.')
    if project.get('selected_graph') not in ids:
        raise ValueError('The selected graph does not exist.')


def _atomic_bytes(path, content):
    """Replace one exact project/backup file, never a data file or plot."""
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary = Path(temporary)
        if temporary.exists():
            temporary.unlink()


class ProjectStore:
    def __init__(self, path, defaults_path):
        self.path = Path(path).expanduser().resolve()
        self.defaults_path = Path(defaults_path).resolve()
        self.digest = None
        self.data = None
        if self.path.exists():
            self.reload()
        else:
            seed = json.loads(self.defaults_path.read_text(encoding='utf-8'))
            self.save(seed)

    def reload(self):
        try:
            raw = self.path.read_bytes()
            project = json.loads(raw)
            validate_project(project)
        except Exception as error:
            raise ValueError(f'Cannot load {self.path}. Existing definitions were preserved. '
                             f'The previous save, if available, is in {self.path.with_suffix(".previous.json")}. {error}') from error
        self.data = project
        self.digest = hashlib.sha256(raw).hexdigest()
        return deepcopy(project)

    def save(self, project):
        project = deepcopy(project)
        validate_project(project)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix('.lock')
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise ProjectConflict('The project is being saved by another session. Try again; '
                                  f'if a crashed session left a stale lock, close all notebooks before removing {lock}.') from error
        try:
            with os.fdopen(handle, 'w') as stream:
                stream.write(str(os.getpid()))
            existing = self.path.read_bytes() if self.path.exists() else None
            digest = hashlib.sha256(existing).hexdigest() if existing is not None else None
            if digest != self.digest:
                raise ProjectConflict('Definitions changed in another notebook or outside this session. '
                                      'Reload saved definitions before editing again; no changes were overwritten.')
            project['revision'] = int(self.data.get('revision', 0) if self.data else project.get('revision', 0)) + 1
            project['saved_at'] = datetime.now().astimezone().isoformat()
            encoded = (json.dumps(project, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
            if existing is not None:
                _atomic_bytes(self.path.with_suffix('.previous.json'), existing)
            _atomic_bytes(self.path, encoded)
            self.digest = hashlib.sha256(encoded).hexdigest()
            self.data = project
        finally:
            lock.unlink()
        return deepcopy(project)

    def add_graph(self, template=None):
        project = deepcopy(self.data)
        base = deepcopy(template or project['new_graph_defaults'])
        existing = {g['name'].casefold() for g in project['graphs']}
        stem = base['name'] + ' copy' if template else 'New graph'
        name, number = stem, 2
        while name.casefold() in existing:
            name = f'{stem} {number}'
            number += 1
        base.update(id=uuid.uuid4().hex, name=name)
        base['definition']['name'] = name
        project['graphs'].append(base)
        project['selected_graph'] = base['id']
        return self.save(project)
