"""Named source folders, following TEM Workbench's project-source workflow.

Only local pointers are edited. The original data source keeps its existing
relative identities; additional sources have separate, readable namespaces.
"""
from pathlib import Path
import os
import uuid


def validate_sources(sources):
    if not isinstance(sources, list) or not sources:
        raise ValueError('Add at least one project folder.')
    ids, names = set(), set()
    legacy = 0
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError('Invalid project folder settings.')
        name, ident = source.get('name'), source.get('id')
        if (not isinstance(name, str) or not name.strip() or name != name.strip()
                or name in ('.', '..', 'Sample data') or any(c in name for c in '/\\\x00')
                or name.casefold() in names):
            raise ValueError('Give each project a unique name without slashes.')
        if not isinstance(ident, str) or not ident or ident in ids:
            raise ValueError('Invalid or duplicate project identity.')
        if not isinstance(source.get('path'), str) or not source['path'].strip():
            raise ValueError('Choose a source folder for every project.')
        if not isinstance(source.get('output', ''), str) or not isinstance(source.get('legacy', False), bool):
            raise ValueError('Invalid project output or identity settings.')
        ids.add(ident); names.add(name.casefold())
        legacy += source.get('legacy', False)
    if legacy > 1:
        raise ValueError('Only the original data source can use legacy identities.')
    return sources


def default_source(path):
    return dict(id='original-data', name='My data', path=str(path), output='', legacy=True)


def new_source():
    return dict(id=uuid.uuid4().hex, name='', path='', output='', legacy=False)


def prefix(source):
    return '' if source.get('legacy') else source['name'] + '/'


def resolve_sources(sources, root, *, output=None, create=False):
    from tensile_startup import resolve_folder
    validate_sources(sources)
    result, paths = [], []
    for source in sources:
        path = resolve_folder(source['path'], root)
        if path.exists() and not path.is_dir():
            raise ValueError(f'Project source is a file, not a folder: {path}')
        if any(path == p or path.is_relative_to(p) or p.is_relative_to(path) for p in paths):
            raise ValueError('Project source folders must not overlap. Choose separate folders.')
        paths.append(path)
        target = resolve_folder(source['output'], root) if source.get('output', '').strip() else None
        result.append({**source, 'path': str(path), 'output': str(target) if target else ''})
    targets = {Path(s['output']) for s in result if s['output']}
    if output is not None:
        targets.add(resolve_folder(output, root))
    for target in targets:
        if any(target == path or path.is_relative_to(target) or target.is_relative_to(path) for path in paths):
            raise ValueError('Keep output folders separate from all project source folders.')
        if target.exists() and not target.is_dir():
            raise ValueError(f'Output is a file: {target}')
    if create:
        for target in targets:
            target.mkdir(parents=True, exist_ok=True)
            if not os.access(target, os.W_OK | os.X_OK):
                raise ValueError(f'Output folder is not writable: {target}')
    return result


def browse(value, root):
    """TEM-style folder listing: Up/Home/path entry, never an unrestricted crawl."""
    from tensile_startup import resolve_folder
    path = resolve_folder(value or str(Path.home()), root)
    if not path.is_dir():
        raise ValueError('That folder is unavailable.')
    children = []
    for child in path.iterdir():
        if child.name.startswith('.'):
            continue
        try:
            if child.is_dir():
                children.append((child.name, str(child.resolve())))
        except OSError:
            continue
    return path, sorted(children, key=lambda row: row[0].casefold())


def folder_snapshot(sources):
    """Metadata-only inventory, including summaries. No curve parsing or hashing.

    Two identical observations are required by FolderChanges before refresh;
    files still being written or synced do not repeatedly invalidate results.
    """
    rows = {}
    for source in sources:
        root = Path(source['path'])
        rows[(source['id'], '')] = root.is_dir()
        if not root.is_dir():
            continue
        def failed(error):
            raise error  # An incomplete walk must never look like deleted data.
        for directory, folders, files in os.walk(root, onerror=failed, followlinks=False):
            folders[:] = sorted(f for f in folders if not f.startswith('.'))
            for name in files:
                if name.startswith('.') or Path(name).suffix.lower() not in ('.csv', '.pdf'):
                    continue
                path = Path(directory) / name
                stat = path.stat()
                rows[(source['id'], path.relative_to(root).as_posix())] = (
                    stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    return rows


class FolderChanges:
    def __init__(self, snapshot):
        self.accepted = snapshot
        self.pending = None

    def observe(self, snapshot):
        if snapshot == self.accepted:
            self.pending = None
            return False
        if snapshot != self.pending:
            self.pending = snapshot
            return False
        return True

    def accept(self, snapshot):
        self.accepted, self.pending = snapshot, None
