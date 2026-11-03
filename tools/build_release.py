"""Build a versioned update ZIP from a clean, committed Git revision."""
import argparse
import json
from pathlib import Path
import stat
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workbench_updates import FORMAT, MANIFEST, managed_name, sha256, validate_manifest, version


def build(root, destination, revision='HEAD'):
    root, destination = Path(root), Path(destination)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    commit = git('rev-parse', revision + '^{commit}').decode().strip()
    number = git('show', commit + ':VERSION').decode().strip()
    version(number)
    files, contents = {}, {}
    for row in git('ls-tree', '-r', '-z', commit).split(b'\0'):
        if not row:
            continue
        metadata, encoded_name = row.split(b'\t', 1)
        mode, kind, object_id = metadata.decode().split()
        name = encoded_name.decode('utf-8')
        managed_name(name)
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ValueError('Linked or unsupported release file: ' + name)
        raw = git('cat-file', 'blob', object_id)
        contents[name] = raw
        files[name] = {'sha256': sha256(raw), 'mode': int(mode[-3:], 8)}
    manifest = validate_manifest({'format': FORMAT, 'version': number, 'commit': commit,
                                  'python': '3.14', 'files': files})
    contents[MANIFEST] = (json.dumps(manifest, indent=2) + '\n').encode()
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / f'Tensile-Workbench-{number}.zip'
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, raw in sorted(contents.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | files.get(name, {}).get('mode', 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    output.with_suffix('.sha256').write_text(sha256(output.read_bytes()) + '  ' + output.name + '\n')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build(ROOT, args.output))
