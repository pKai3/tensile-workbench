"""Tiny synthetic ruled PDF tables, with no research data or authoring dependency."""
from pathlib import Path


def write_pdf(path, pages):
    objects = [b'', b'', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    page_ids = []
    for tables in pages:
        commands, top = ['0.3 w'], 750
        for table in tables:
            widths = [35] + [165] * (len(table[0]) - 1)
            for row in table:
                height = 12 + 12 * max(len(str(cell).split('\n')) for cell in row)
                left = 30
                for width, cell in zip(widths, row):
                    commands.append(f'{left} {top-height} {width} {height} re S')
                    for line, text in enumerate(str(cell).split('\n')):
                        text = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
                        commands.append(f'BT /F1 9 Tf 1 0 0 1 {left+5} {top-14-line*12} Tm ({text}) Tj ET')
                    left += width
                top -= height
            top -= 30
        stream = '\n'.join(commands).encode('latin-1')
        page_id, stream_id = len(objects) + 1, len(objects) + 2
        page_ids.append(page_id)
        objects.append((f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 650 800] '
                        f'/Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>').encode())
        objects.append(f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream')
    objects[0] = b'<< /Type /Catalog /Pages 2 0 R >>'
    objects[1] = ('<< /Type /Pages /Count ' + str(len(page_ids)) + ' /Kids [' +
                  ' '.join(f'{ident} 0 R' for ident in page_ids) + '] >>').encode()
    payload = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(payload))
        payload.extend(f'{index} 0 obj\n'.encode() + body + b'\nendobj\n')
    start = len(payload)
    payload.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        payload.extend(f'{offset:010d} 00000 n \n'.encode())
    payload.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    Path(path).write_bytes(payload)
