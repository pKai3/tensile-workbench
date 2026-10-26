"""Conservative import of numbered, text-based Instron PDF result tables.

Use table cells and printed row IDs, never graph pixels, OCR, row positions or
numerical similarity. Separate column panels are joined only by their row ID.
"""
import hashlib
from pathlib import Path
import re

import numpy as np

from tensile_instron import _field, _normal, _number, reported_resolution


def _row_id(value):
    return re.fullmatch(r'([xX]?)\s*(\d+)', str(value or '').strip())


def _column(header):
    text = ' '.join(str(header or '').split())
    unit = re.search(r'(\[[^\[\]]+\]|\((?:MPa|GPa|Pa|mm|m|%|percent)\))\s*$', text, re.I)
    heading = text[:unit.start()].strip() if unit else text
    field, kind = _field(heading)
    return heading, field, kind, unit[0] if unit else ''


def _merge_table(table, page_number, records):
    if not table or len(table[0]) < 2:
        return
    # Report layouts may split a heading and its unit into separate rows.
    first_data = next((i for i, row in enumerate(table) if row and _row_id(row[0])), None)
    if first_data is None or first_data == 0:
        return  # No reliable heading: do not guess continuation columns.
    width = len(table[0])
    if any(len(row) != width for row in table[:first_data]):
        return
    headers = [' '.join(str(row[i] or '') for row in table[:first_data]) for i in range(width)]
    if _normal(headers[0]) not in ('', 'specimen', 'specimen number', 'specimen no.', 'specimen #', 'no.'):
        return
    columns = [_column(header) for header in headers]
    if not any(field or 'specimen text input' in _normal(heading) for heading, field, _, _ in columns[1:]):
        return  # Graph axes, page furniture and aggregate tables aren't results.
    seen = set()
    for row in table[first_data:]:
        ident = _row_id(row[0]) if row else None
        if ident is None or len(row) != width or int(ident[2]) < 1:
            continue  # Mean / SD / CV / page footers do not become specimens.
        index = int(ident[2])
        item = records.setdefault(index, dict(index=index, excluded=False, label='', values={},
            resolution={}, notes=[], pages=[], _labels=set(), _conflicts=set()))
        item['excluded'] |= bool(ident[1])
        if page_number not in item['pages']:
            item['pages'].append(page_number)
        if index in seen:
            item['notes'].append('Name: duplicate specimen row within a PDF table; review identity.')
        seen.add(index)
        for token, (heading, field, kind, unit) in zip(row[1:], columns[1:]):
            text = ' '.join(str(token or '').split())
            if 'specimen text input' in _normal(heading) and text:
                item['_labels'].add(text)
            if not field:
                continue
            value = _number(text, unit, kind)
            precision = _number(reported_resolution(text), unit, kind)
            old = item['values'].get(field, np.nan)
            if field in item['_conflicts']:
                continue
            if np.isfinite(old) and np.isfinite(value) and not np.isclose(old, value, rtol=0, atol=1e-9):
                item['_conflicts'].add(field)
                item['values'][field] = np.nan
                item['resolution'][field] = np.nan
                item['notes'].append(f'Conflicting PDF values left blank: {field}')
            elif np.isfinite(value):
                item['values'][field] = value
                previous = item['resolution'].get(field, precision)
                item['resolution'][field] = min(previous, precision)
            else:
                item['values'].setdefault(field, np.nan)
                if text not in ('', '—', '-', '---', '----', '-----'):
                    item['notes'].append(f'{heading}: missing/unsupported PDF unit or numeric value')


def read_summary_pdf(path, *, metadata=None):
    """Return per-row values and precision; explain unsupported reports explicitly."""
    path = Path(path)
    info = metadata if metadata is not None else {}
    info.update(summary_present=True, readable=False, error='')
    try:
        import pdfplumber
    except ImportError:
        info['error'] = 'PDF reader is unavailable. Relaunch through the workbench launcher to update dependencies.'
        return []
    records = {}
    try:
        with pdfplumber.open(path) as report:
            for page_number, page in enumerate(report.pages, 1):
                for table in page.extract_tables():
                    _merge_table(table, page_number, records)
                page.close()
        info['readable'] = True
        if not records:
            info['error'] = ('No supported numbered text tables found in the PDF. '
                             'Scanned reports and graph images are not imported; export a summary CSV if possible.')
            return []
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception as error:
        # A damaged/encrypted report must never prevent raw curves from loading.
        # Do not use partial values from a report that failed partway through.
        info['error'] = f'PDF could not be read ({type(error).__name__}); supply an unlocked, readable report or a summary CSV.'
        return []
    for item in records.values():
        labels = sorted(item.pop('_labels'))
        item.pop('_conflicts')
        item['label'] = ' / '.join(labels)
        if len(labels) > 1:
            item['notes'].append('Name: conflicting operator specimen labels within the PDF.')
        item.update(source=str(path), sha256=digest, format='PDF')
        item['notes'] = list(dict.fromkeys(item['notes']))
    return list(records.values())
