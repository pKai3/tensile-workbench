"""Read Instron summary CSVs only. Never infer specimen identity from a value."""
import csv
import hashlib
from pathlib import Path
import re
import numpy as np


def _normal(text):
    return ' '.join(str(text).strip().lower().split())


def _field(header):
    text = _normal(header)
    if 'stress at yield' in text and re.search(r'offset 0[.,]2\s*%', text):
        return 'ys', 'stress'
    if 'stress at maximum force' in text:
        return 'uts', 'stress'
    if 'modulus' in text and 'young' in text:
        return 'e', 'modulus'
    if 'strain (strain 1)' in text and 'at break' in text:
        return 'el', 'strain'
    if 'strain (strain 1)' in text and 'at maximum force' in text:
        return 'uniform', 'strain'
    if text in ('thickness', 'width', 'strain 1 gauge length'):
        return {'thickness': 'thickness', 'width': 'width', 'strain 1 gauge length': 'gauge'}[text], 'length'
    return None, None


def _number(value, unit, kind):
    try:
        number = float(str(value).strip())
    except ValueError:
        return np.nan
    if not np.isfinite(number):
        return np.nan
    unit = unit.strip().strip('()[]').strip().lower()
    scales = {'stress': {'mpa': 1, 'pa': 1e-6, 'gpa': 1000},
              'modulus': {'gpa': 1, 'mpa': .001, 'pa': 1e-9},
              'strain': {'%': 1, 'percent': 1}, 'length': {'mm': 1, 'm': 1000}}
    return number * scales.get(kind, {}).get(unit, np.nan)


def read_summary_csv(path):
    """Return the first supported Results Table; stop before raw time-series data."""
    path = Path(path)
    for encoding in ('utf-8-sig', 'cp1252'):
        for delimiter in (',', ';', '\t'):
            rows, header, units = [], None, None
            try:
                with path.open(encoding=encoding, newline='') as stream:
                    for row in csv.reader(stream, delimiter=delimiter):
                        normal = [_normal(value) for value in row]
                        if 'time' in normal and ('tensile stress' in normal or 'stress' in normal):
                            break
                        if header is None:
                            if any('stress at maximum force' in value or 'stress at yield' in value for value in normal):
                                header = row
                            continue
                        if units is None:
                            units = row
                            continue
                        if not row or not any(str(value).strip() for value in row):
                            break
                        match = re.fullmatch(r'([xX]?)(\d+)', row[0].strip())
                        if not match or len(row) != len(header):
                            continue
                        item = {'index': int(match[2]), 'excluded': bool(match[1]), 'label': '',
                                'values': {}, 'source': str(path), 'notes': []}
                        for index, label in enumerate(header):
                            if 'specimen text input' in _normal(label):
                                item['label'] = row[index].strip()
                            field, kind = _field(label)
                            if field:
                                unit = units[index] if index < len(units) else ''
                                item['values'][field] = _number(row[index], unit, kind)
                                if row[index].strip() not in ('', '-----', '----', '---') and not np.isfinite(item['values'][field]):
                                    item['notes'].append(f'{label}: missing/unsupported unit or numeric value')
                        rows.append(item)
                if rows:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    for item in rows:
                        item['sha256'] = digest
                    return rows
            except (OSError, UnicodeError, csv.Error):
                continue
    return []


def _export_identity(source):
    """Bind a curve to its Instron export dataset and row number, not its label."""
    source = Path(source)
    parent = source.parent.name
    match = re.fullmatch(r'(.+)\.(?:is|id)_tens_Exports', parent, re.IGNORECASE)
    if not match:
        return None, None
    dataset = match[1]
    suffix = source.stem[len(dataset):] if source.stem.casefold().startswith(dataset.casefold() + '_') else ''
    index = re.fullmatch(r'_(\d+)(?:_1)?', suffix)
    return dataset, int(index[1]) if index else None


class InstronSummaries:
    def __init__(self, data_directory):
        self.root = Path(data_directory)
        self._csv = {}
        self._groups = {}

    def read(self, path):
        key = str(path)
        if key not in self._csv:
            self._csv[key] = read_summary_csv(path)
        return self._csv[key]

    def match(self, group, record):
        source = Path(record['source_file'])
        embedded = self.read(source)
        dataset, index = _export_identity(source)
        if embedded:
            candidates = embedded if len(embedded) == 1 else [row for row in embedded if row['index'] == index]
            method = 'Embedded CSV summary'
        else:
            if group not in self._groups:
                self._groups[group] = [(path, self.read(path)) for path in sorted((self.root / group).rglob('*.csv'))
                                       if not path.name.startswith('!') and not re.search(r'\.(?:is|id)_tens_Exports$', path.parent.name, re.I)]
            candidates = []
            if dataset is not None and index is not None:
                for path, rows in self._groups[group]:
                    # Instron names group summaries dataset.csv, dataset_1.csv,
                    # or dataset_1_1.csv. Do not attach unrelated summaries.
                    if re.fullmatch(re.escape(dataset) + r'(?:_\d+){0,2}', path.stem, re.I):
                        candidates.extend(row for row in rows if row['index'] == index)
            method = 'Dataset + Instron row number'
            if not candidates:
                candidates = [row for _, rows in self._groups[group] for row in rows
                              if row['label'].casefold() == source.stem.casefold()]
                if candidates:
                    method = 'Exact specimen label'
        result = {'values': {}, 'status': 'Unavailable', 'notes': 'No matching Instron summary CSV.',
                  'source': '', 'sha256': '', 'index': index, 'label': '', 'excluded': False}
        if not candidates:
            if dataset is None or index is None:
                result['notes'] = 'No embedded summary or unambiguous dataset/row identity. No numerical matching attempted.'
            return result
        # Multiple summary revisions may agree numerically but differ in labels.
        # Preserve non-conflicting fields; never select a conflicting value.
        values, conflicts = {}, []
        for field in {key for row in candidates for key in row['values']}:
            available = [row['values'][field] for row in candidates if np.isfinite(row['values'].get(field, np.nan))]
            if not available:
                values[field] = np.nan
            elif np.allclose(available, available[0], rtol=0, atol=1e-9):
                values[field] = available[0]
            else:
                values[field] = np.nan
                conflicts.append(field)
        labels = sorted({row['label'] for row in candidates if row['label']})
        notes = sorted({note for row in candidates for note in row['notes']})
        if conflicts:
            notes.append('Conflicting summary values left blank: ' + ', '.join(sorted(conflicts)))
        if len(labels) > 1:
            notes.append('Specimen labels differ between summary revisions; match uses export row number.')
        excluded = any(row['excluded'] for row in candidates)
        if excluded:
            notes.append('Marked excluded (X) in an Instron summary; not automatically excluded here.')
        result.update(values=values, status='Conflicting summaries' if conflicts else method,
                      notes=' '.join(notes), source='; '.join(sorted({row['source'] for row in candidates})),
                      sha256='; '.join(sorted({row['sha256'] for row in candidates})),
                      index=candidates[0]['index'], label=' / '.join(labels), excluded=excluded)
        return result
