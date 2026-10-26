"""Read Instron summaries, preferring CSV to PDF. Never match by a test value."""
import csv
import hashlib
import io
from pathlib import Path
import re
from decimal import Decimal, InvalidOperation
import numpy as np
from tensile_selection import csv_files, data_files
from tensile_columns import is_measurement_header


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


def reported_resolution(value):
    """Least significant printed digit, including trailing zeros/scientific notation."""
    try:
        number = Decimal(str(value).strip())
        if number.is_finite():
            result = float(Decimal(10) ** number.as_tuple().exponent)
            if np.isfinite(result) and result > 0:
                return result
    except (InvalidOperation, ValueError, OverflowError):
        pass
    return np.nan


def raw_check_precision(frame, has_units, stress_column, strain_column, metadata):
    """Record CSV precision before float conversion, never from filtered curves."""
    raw = frame.iloc[1:] if has_units else frame
    result = {}
    for key, column, values in (('uts', stress_column, metadata['stress']),
                                ('el', strain_column, metadata['strain'])):
        ids = np.flatnonzero(np.isfinite(values))
        if column is None or not len(ids):
            continue
        maximum = float(np.max(values[ids]))
        peak_ids = ids[values[ids] == maximum]
        resolutions = []
        for index in peak_ids:
            token = raw.iloc[int(index)][column]
            try:
                original = float(token)
                # Conversion scale inferred from this exact original/converted
                # pair, so the check uses the loader's existing unit handling.
                scale = abs(values[index] / original) if original != 0 else np.nan
                resolution = reported_resolution(token) * scale
                if np.isfinite(resolution):
                    resolutions.append(resolution)
            except (ValueError, TypeError):
                pass
        result[key] = max(resolutions) if resolutions else np.nan
    return result


def _verify_reference(result, record, name_ok, name_failures=()):
    """Verify an identity-selected candidate; never search for the closest value."""
    measured = record.get('_measured_record', record)
    meta = measured.get('_acquisition', {})
    failures = list(name_failures)
    if not name_ok and not failures:
        failures.append('Name: no unambiguous dataset/export-row or exact-label match.')
    audit = {}
    # EL is not an identity check: Instron's break result and the CSV endpoint
    # represent different endpoint definitions, even for the correct specimen.
    for key, array, title, unit in (('uts', 'stress', 'UTS', 'MPa'),):
        values = np.asarray(meta.get(array, []), dtype=float)
        finite = values[np.isfinite(values)]
        raw = float(np.max(finite)) if len(finite) else np.nan
        reported = result['values'].get(key, np.nan)
        resolution = result.get('resolution', {}).get(key, np.nan)
        raw_resolution = meta.get('check_resolution', {}).get(key, np.nan)
        # UTS uses printed-digit rounding, not a fitted curve or EL agreement.
        tolerance = (resolution / 2 + (raw_resolution / 2 if np.isfinite(raw_resolution) else 0)
                     + 1e-9 * max(1, abs(raw), abs(reported))) if np.isfinite(resolution) else np.nan
        difference = raw - reported
        passed = bool(np.isfinite(raw) and np.isfinite(reported) and np.isfinite(tolerance)
                      and abs(difference) <= tolerance + 1e-12)
        audit.update({f'{title} raw CSV maximum ({unit})': raw,
                      f'{title} Instron value ({unit})': reported,
                      f'{title} check difference ({unit})': difference,
                      f'{title} check tolerance ({unit})': tolerance})
        if not np.isfinite(raw):
            failures.append(f'{title}: original recorded {array} unavailable; cannot verify.')
        elif not np.isfinite(reported) or not np.isfinite(tolerance):
            failures.append(f'{title}: summary value missing, conflicting or unreadable; cannot verify.')
        elif not passed:
            detail = (f'{title}: CSV maximum {raw:.2f} {unit} vs Instron {reported:.2f} {unit} '
                      f'(Δ {difference:+.2f}; tolerance ±{tolerance:.2f}; checked before display rounding).')
            failures.append(detail)
    for note in result.get('notes', '').split('\n'):
        if note and note not in failures:
            failures.append(note)
    result['check_failures'] = list(dict.fromkeys(failures))
    result['check_values'] = audit
    return result


def read_summary_csv(path, *, metadata=None):
    """Return the first supported Results Table; stop before raw time-series data."""
    path = Path(path)
    info = metadata if metadata is not None else {}
    info.update(summary_present=False, readable=False, is_curve=False)
    for encoding in ('utf-8-sig', 'cp1252'):
        for delimiter in (',', ';', '\t'):
            rows, header, units = [], None, None
            try:
                with path.open(encoding=encoding, newline='') as stream:
                    for row in csv.reader(stream, delimiter=delimiter):
                        normal = [_normal(value) for value in row]
                        info['readable'] = True
                        if is_measurement_header(row):
                            info['is_curve'] = True
                            if not rows:
                                return []  # Never scan the numeric body looking for a summary.
                            break
                        if any('results table' in value for value in normal):
                            info['summary_present'] = True
                        if header is None:
                            if any('stress at maximum force' in value or 'stress at yield' in value for value in normal):
                                header = row
                                info['summary_present'] = True
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
                                'values': {}, 'resolution': {}, 'source': str(path), 'notes': [],
                                'format': 'CSV', 'pages': []}
                        for index, label in enumerate(header):
                            if 'specimen text input' in _normal(label):
                                item['label'] = row[index].strip()
                            field, kind = _field(label)
                            if field:
                                unit = units[index] if index < len(units) else ''
                                item['values'][field] = _number(row[index], unit, kind)
                                item['resolution'][field] = _number(reported_resolution(row[index]), unit, kind)
                                if row[index].strip() not in ('', '-----', '----', '---') and not np.isfinite(item['values'][field]):
                                    item['notes'].append(f'{label}: missing/unsupported unit or numeric value')
                        rows.append(item)
                info['readable'] = True
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


def _summary_stem(path):
    # Instron reports normally retain the test-method suffix: Batch.is_tens.pdf.
    stem = path.stem
    return re.sub(r'\.(?:is|id)_tens(?=(_\d+){0,2}$)', '', stem, flags=re.I) if path.suffix.lower() == '.pdf' else stem


def _dataset_summary(path, dataset):
    return bool(dataset and re.fullmatch(re.escape(dataset) + r'(?:_\d+){0,2}', _summary_stem(path), re.I))


def _summary_candidates(source, embedded, group_rows):
    """Same identity rules for the lightweight catalogue and analysed records."""
    dataset, index = _export_identity(source)
    if embedded:
        return (embedded if len(embedded) == 1 else [r for r in embedded if r['index'] == index],
                'Embedded CSV summary', [])
    candidates, review_rows = [], []
    if dataset is not None:
        for path, rows in group_rows:
            if _dataset_summary(path, dataset):
                review_rows.extend(rows)
                candidates.extend(row for row in rows if row['index'] == index)
    method = 'Dataset + Instron row number'
    if not candidates:
        candidates = [row for _, rows in group_rows for row in rows
                      if row['label'].casefold() == source.stem.casefold()]
        if candidates:
            method = 'Exact specimen label'
    return candidates, method, review_rows


def read_catalogue_csv(path, strain_names, load_names, *, byte_limit=262144, metadata=None):
    """Read only a bounded preamble, never numeric arrays, full-file hashes or fits.

    Look for the same complete measurement column names as the curve loader.
    Parse quoted/multiline summary fields normally, stopping at the measurement
    header. An unrecognised/truncated preamble cannot invent a specimen number.
    """
    strain_names = {_normal(name) for name in strain_names}
    load_names = {_normal(name) for name in load_names}
    info = metadata if metadata is not None else {}
    info.update(summary_present=False, readable=False, is_curve=False)

    def parse(text):
        best = []
        for delimiter in (',', ';', '\t'):
            rows, header, units, ended = [], None, False, False
            try:
                for row in csv.reader(io.StringIO(text, newline=''), delimiter=delimiter):
                    names = {_normal(value) for value in row}
                    if any('results table' in value for value in names):
                        info['summary_present'] = True
                    if names & strain_names and names & load_names:
                        info['is_curve'] = True
                        return True, rows
                    if ended:
                        continue
                    if header is None:
                        if any('stress at maximum force' in value or 'stress at yield' in value for value in names):
                            header = row
                            info['summary_present'] = True
                        continue
                    if not units:
                        units = True
                        continue
                    if not row or not any(value.strip() for value in row):
                        ended = True
                        continue
                    match = re.fullmatch(r'[xX]?(\d+)', row[0].strip())
                    if not match or len(row) != len(header):
                        continue
                    label = next((row[i].strip() for i, name in enumerate(header)
                                  if 'specimen text input' in _normal(name)), '')
                    rows.append({'index': int(match[1]), 'label': label})
            except csv.Error:
                continue
            if len(rows) > len(best):
                best = rows
        return False, best

    payload = bytearray()
    try:
        with Path(path).open('rb') as stream:
            while len(payload) < byte_limit:
                chunk = stream.read(min(4096, byte_limit - len(payload)))
                info['readable'] = True
                payload.extend(chunk)
                try:
                    text = payload.decode('utf-8-sig')
                except UnicodeDecodeError:
                    text = payload.decode('cp1252', errors='replace')
                # Do not parse a partial last physical line until EOF.
                if chunk:
                    end = max(text.rfind('\n'), text.rfind('\r'))
                    text = text[:end + 1] if end >= 0 else ''
                result = parse(text)
                if result[0] or not chunk:
                    return result
    except OSError:
        pass
    return False, []  # Unreadable or over-limit metadata remains unassigned.


def _identity_review(result, record, summary_rows):
    """Read-only UTS-compatible alternatives within the named dataset, never rematch."""
    source = Path(record['source_file'])
    dataset, export_row = _export_identity(source)
    result.update(csv_filename=source.name, export_row=export_row, dataset=dataset or '',
                  uts_review_candidates=[])
    audit = result.get('check_values', {})
    raw = audit.get('UTS raw CSV maximum (MPa)', np.nan)
    difference = audit.get('UTS check difference (MPa)', np.nan)
    tolerance = audit.get('UTS check tolerance (MPa)', np.nan)
    if not np.isfinite(raw) or (np.isfinite(difference) and np.isfinite(tolerance)
                               and abs(difference) <= tolerance + 1e-12):
        return result
    if not dataset or not summary_rows:
        return result
    meta = record.get('_measured_record', record).get('_acquisition', {})
    raw_resolution = meta.get('check_resolution', {}).get('uts', np.nan)
    by_index = {}
    for row in summary_rows:
        by_index.setdefault(row['index'], []).append(row)
    for index, rows in sorted(by_index.items()):
        # Do not recommend one revision when another disagrees, or treat
        # duplicate rows within a single summary as an unambiguous candidate.
        values = [row['values'].get('uts', np.nan) for row in rows]
        resolutions = [row.get('resolution', {}).get('uts', np.nan) for row in rows]
        labels = {row['label'] for row in rows if row['label']}
        if (len({row['source'] for row in rows}) != len(rows) or len(labels) > 1
                or not all(np.isfinite(values)) or not all(np.isfinite(resolutions))
                or not np.allclose(values, values[0], rtol=0, atol=1e-9)):
            continue
        reported = values[0]
        allowed = (min(resolutions) / 2 + (raw_resolution / 2 if np.isfinite(raw_resolution) else 0)
                   + 1e-9 * max(1, abs(raw), abs(reported)))
        if abs(raw - reported) > allowed + 1e-12:
            continue
        result['uts_review_candidates'].append({
            'row': index, 'label': next(iter(labels), ''), 'uts_mpa': reported,
            'difference_mpa': raw - reported, 'tolerance_mpa': allowed,
            'sources': sorted({row['source'] for row in rows}),
            'excluded': any(row['excluded'] for row in rows),
        })
    hints = []
    for candidate in result['uts_review_candidates']:
        sources = ', '.join(sorted({Path(path).name for path in candidate['sources']}))
        label = candidate['label'] or '(no operator label)'
        hints.append(f'row {candidate["row"]} · {label} · {candidate["uts_mpa"]:.2f} MPa'
                     f' [{sources}]' + (' (Instron excluded)' if candidate['excluded'] else ''))
    result['identity_review_note'] = ('UTS-compatible rows — review only:\n' + '\n'.join(hints)
        if hints else 'No UTS-compatible alternative in this dataset’s available summaries.')
    result['check_failures'].append(result['identity_review_note'])
    return result


class InstronSummaries:
    def __init__(self, data_directory, group_directories=None):
        self.root = Path(data_directory)
        self.group_directories = group_directories or {}
        self._csv = {}
        self._csv_info = {}
        self._groups = {}
        self._catalogues = {}
        self._pdf_groups = {}
        self._pdf = {}
        self._pdf_info = {}

    def _choose_candidates(self, group, source, embedded, group_rows, info):
        """CSV takes precedence even if its row is missing or its values conflict."""
        candidates, method, review = _summary_candidates(source, embedded, group_rows)
        dataset, _ = _export_identity(source)
        known_csv = [(path, rows) for path, rows in group_rows
                     if rows or info.get(str(path), {}).get('summary_present')
                     or not info.get(str(path), {}).get('readable', True)
                     or (_dataset_summary(path, dataset) and not info.get(str(path), {}).get('is_curve', True))]
        relevant_csv = [path for path, _ in known_csv if dataset is None or _dataset_summary(path, dataset)]
        if info.get(str(source), {}).get('summary_present'):
            relevant_csv.append(source)
        if embedded or candidates or relevant_csv:
            return candidates, method, review, relevant_csv, []
        if group not in self._pdf_groups:
            directory = self.group_directories.get(group, self.root / group)
            self._pdf_groups[group] = data_files(directory, '.pdf')
        paths = self._pdf_groups[group]
        # Named reports first. Exact operator-label fallback can handle a renamed
        # report, but never borrow a row number from a different dataset.
        named = [path for path in paths if _dataset_summary(path, dataset)]
        selected = named or paths
        pdf_rows, errors = [], []
        for path in selected:
            key = str(path)
            if key not in self._pdf:
                from tensile_instron_pdf import read_summary_pdf
                self._pdf_info[key] = {}
                self._pdf[key] = read_summary_pdf(path, metadata=self._pdf_info[key])
            pdf_rows.append((path, self._pdf[key]))
            if self._pdf_info[key].get('error'):
                errors.append(f'{path.name}: {self._pdf_info[key]["error"]}')
        if pdf_rows:
            candidates, method, review = _summary_candidates(source, [], pdf_rows)
        # Unknown CSV identities still need review, even if no matching report exists.
        inputs = selected or [path for path, _ in known_csv]
        return candidates, method, review, inputs, errors

    def catalogue(self, group, sources, strain_names, load_names):
        """Cached file/label inventory. This does not verify UTS or calculate properties."""
        if group not in self._catalogues:
            strain_names = {_normal(name) for name in strain_names}
            load_names = {_normal(name) for name in load_names}
            info = {str(path): {} for path in sources}
            metadata = {path: read_catalogue_csv(path, strain_names, load_names, metadata=info[str(path)]) for path in sources}
            group_rows = [(path, rows) for path, (_, rows) in metadata.items()
                          if not re.search(r'\.(?:is|id)_tens_Exports$', path.parent.name, re.I)]
            records = []
            for source, (is_curve, embedded) in metadata.items():
                if not is_curve:
                    continue
                candidates, _, _, _, _ = self._choose_candidates(group, source, embedded, group_rows, info)
                labels = sorted({row['label'] for row in candidates if row['label']})
                records.append({'source_file': str(source), 'sample': source.stem,
                                'specimen_label': ' / '.join(labels)})
            self._catalogues[group] = records
        return self._catalogues[group]

    def read(self, path):
        key = str(path)
        if key not in self._csv:
            self._csv_info[key] = {}
            self._csv[key] = read_summary_csv(path, metadata=self._csv_info[key])
        return self._csv[key]

    def match(self, group, record):
        source = Path(record['source_file'])
        embedded = self.read(source)
        dataset, index = _export_identity(source)
        if not embedded:
            if group not in self._groups:
                directory = self.group_directories.get(group, self.root / group)
                self._groups[group] = [(path, self.read(path)) for path in csv_files(directory)
                                       if not re.search(r'\.(?:is|id)_tens_Exports$', path.parent.name, re.I)]
        candidates, method, review_rows, inputs, errors = self._choose_candidates(
            group, source, embedded, self._groups.get(group, []), self._csv_info)
        result = {'values': {}, 'status': 'Unavailable', 'notes': '', 'source_note': '',
                  'source': '', 'source_format': '', 'source_pages': '', 'availability': 'unavailable',
                  'sha256': '', 'index': index, 'label': '', 'excluded': False}
        if not candidates:
            if not inputs:
                result.update(status='CSV only', availability='csv_only',
                    notes='No Instron summary CSV or PDF. Raw curves and Calc values remain available; '
                          'Instron comparisons and operator specimen labels are unavailable.',
                    check_failures=[], check_values={})
            else:
                reason = (' '.join(errors) if errors else
                    'No matching specimen row in the available summary. Check the dataset/export-row names '
                    'or the exact operator specimen label, and that the summary contains a readable results table.')
                result.update(notes=reason, check_failures=['Instron summary: ' + reason], check_values={})
            return _identity_review(result, record, review_rows)
        # Multiple summary revisions may agree numerically but differ in labels.
        # Preserve non-conflicting fields; never select a conflicting value.
        values, resolution, conflicts = {}, {}, []
        for field in {key for row in candidates for key in row['values']}:
            available = [row['values'][field] for row in candidates if np.isfinite(row['values'].get(field, np.nan))]
            if not available:
                values[field] = np.nan
            elif np.allclose(available, available[0], rtol=0, atol=1e-9):
                values[field] = available[0]
                precision = [row.get('resolution', {}).get(field, np.nan) for row in candidates
                             if np.isfinite(row['values'].get(field, np.nan))]
                precision = [value for value in precision if np.isfinite(value)]
                resolution[field] = min(precision) if precision else np.nan
            else:
                values[field] = np.nan
                conflicts.append(field)
        labels = sorted({row['label'] for row in candidates if row['label']})
        notes = sorted({note for row in candidates for note in row['notes']})
        if conflicts:
            notes.append('Conflicting summary values left blank: ' + ', '.join(sorted(conflicts)))
        excluded = any(row['excluded'] for row in candidates)
        if excluded:
            notes.append('Marked excluded (X) in an Instron summary; not automatically excluded here.')
        result.update(values=values, resolution=resolution, status='Conflicting summaries' if conflicts else method,
                      notes='\n'.join(notes), source='; '.join(sorted({row['source'] for row in candidates})),
                      sha256='; '.join(sorted({row['sha256'] for row in candidates})),
                      index=candidates[0]['index'], label=' / '.join(labels), excluded=excluded)
        result['availability'] = 'matched'
        result['source_format'] = 'PDF' if all(Path(row['source']).suffix.lower() == '.pdf' for row in candidates) else 'CSV'
        if result['source_format'] == 'PDF':
            result['status'] += ' (PDF fallback)'
            result['source_note'] = 'Instron values imported from a PDF summary; precision follows its printed digits.'
            result['source_pages'] = '; '.join(sorted({Path(row['source']).name + ': ' +
                ', '.join(map(str, row.get('pages', []))) for row in candidates}))
            # An unreadable revision cannot silently disappear beside a valid one.
            if errors:
                result['notes'] += ('\n' if result['notes'] else '') + '\n'.join(errors)
        name_ok = (method == 'Dataset + Instron row number' or
                   (method == 'Exact specimen label' and len(candidates) == 1) or
                   (method == 'Embedded CSV summary' and
                    ((index is not None and all(row['index'] == index for row in candidates)) or
                     (index is None and len(candidates) == 1 and
                      candidates[0]['label'].casefold() == source.stem.casefold()))))
        name_failures = []
        if method == 'Exact specimen label' and len(candidates) > 1:
            name_failures.append('Name: exact specimen label appears in multiple summary rows/files; review identity.')
        if len({(row['source'], row['index']) for row in candidates}) < len(candidates):
            name_failures.append('Name: duplicate row number within a summary file; review identity.')
        if method == 'Embedded CSV summary' and index is not None and not name_ok:
            name_failures.append(f'Name: export row {index} differs from the embedded summary row.')
        if len(labels) > 1:
            name_failures.append('Name: conflicting operator specimen labels across summary revisions.')
        return _identity_review(_verify_reference(result, record, name_ok, name_failures), record, review_rows)
