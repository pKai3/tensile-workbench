"""Portable specimen identities and hard-ignore rules shared by all data readers."""
import os
from pathlib import Path, PurePosixPath

SAMPLE_GROUP_PREFIX = 'Sample data / '
SAMPLE_ID_PREFIX = 'sample-data://'


def csv_files(root):
    """Do not enter marked folders or read CSVs containing ! anywhere in a name."""
    root = Path(root)
    if '!' in root.name:
        return []
    found = []
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(name for name in folders if '!' not in name)
        found.extend(Path(directory) / name for name in sorted(files)
                     if '!' not in name and name.lower().endswith('.csv'))
    return sorted(found)


def valid_specimen_id(value):
    """Research IDs remain relative paths; bundled IDs have a separate namespace."""
    if isinstance(value, str) and value.startswith(SAMPLE_ID_PREFIX):
        value = value[len(SAMPLE_ID_PREFIX):]
    return (isinstance(value, str) and bool(value) and '\\' not in value
            and not PurePosixPath(value).is_absolute()
            and all(part not in ('', '.', '..') for part in value.split('/')))


def specimen_id(record):
    # Fallback supports callers that construct records outside PreviewSession.
    return record.get('specimen_id', record['source_file'])


def is_included(record, spec):
    return specimen_id(record) not in spec.get('specimen_exclusions', {})
