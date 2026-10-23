"""Odtwarza słownik z tabel opublikowanych przez producenta POZYTON.

Wymaga Popplera (pdftotext) oraz oryginalnego PDF wskazanego w docs/obis-pl.md.
Nie pobiera ani nie rozpowszechnia pełnych dokumentów normatywnych.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

PDF_SHA256 = '0c3ac4ace544b4746fce7c5c667081682a8c970babe7ce74a1cf50a25ed545f6'
URL = 'https://pozyton.com.pl/wp-content/uploads/2024/05/instrukcja-operatorska-le-23-4.pdf'


def build(pdf):
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != PDF_SHA256:
        raise ValueError('PDF ma inną sumę kontrolną. Nową wersję dokumentu trzeba najpierw zweryfikować.')
    pages = subprocess.check_output(['pdftotext', '-layout', str(pdf), '-']).decode().split('\f')
    entries = {}
    # Zakres ogranicza się do standardowych wielkości elektrycznych.
    # Wyklucza m.in. opisy konfiguracji producenta (C >= 128) i jego rozszerzenia E >= 128.
    for number in (87, 89, 90, 91):
        for line in pages[number-1].splitlines():
            match = re.match(r'^\s*(\d+)\.(\d+)\.(\d+|x)\s+(.+)$', line)
            if not match:
                continue
            c, d, e, text = match.groups()
            c, d = int(c), int(d)
            if not 1 <= c <= 81 or d not in (3, 4, 5, 6, 7, 8, 15):
                continue
            text = re.sub(r'\s+', ' ', text.strip())
            if e == 'x' and d == 8 and c <= 10:
                base = text.split(' x =')[0]
                for rate in range(5):
                    label = base + (' — bezstrefowo' if rate == 0 else f' — strefa {rate}')
                    entries[f'1:{c}.{d}.{rate}'] = {'text': label, 'source': 'pozyton-le23-008', 'page': number}
            elif e == 'x' and d == 7 and c in (31, 32, 51, 52, 71, 72):
                base = text.split(' x=')[0]
                for harmonic in range(1, 64):
                    entries[f'1:{c}.{d}.{harmonic}'] = {'text': f'{harmonic}. {base[0].lower()+base[1:]}',
                                                        'source': 'pozyton-le23-008', 'page': number}
            elif e.isdigit() and int(e) < 128:
                entries[f'1:{c}.{d}.{int(e)}'] = {'text': text, 'source': 'pozyton-le23-008', 'page': number}
    # C.6.0 i C.6.3: kody abstrakcyjne, więc osobna przestrzeń A=0.
    entries['0:96.6.0'] = {'text': 'Czas użycia baterii', 'source': 'pozyton-le23-008', 'page': 86}
    return {'version': 1, 'language': 'pl', 'sources': {
        'pozyton-le23-008': {'title': 'POZYTON LE-23 — instrukcja obsługi TK/3001/057/008',
                              'url': URL, 'sha256': PDF_SHA256},
        'dlms-bluebook17': {'title': 'DLMS UA Blue Book, wyd. 17, część 1 — oficjalny wyciąg',
                           'url': 'https://www.dlms.com/wp-content/uploads/2025/06/Excerpts-DLMS-Blue-Book-Ed-17-part-1-V1.0.pdf',
                           'sha256': '45de9c791f1f42ac9074b7fd6cc3e4ad8247784e98069c0e67b44900ef67b9fb',
                           'sections': '5.2, 5.3, 5.5 i 5.6'}}, 'entries': dict(sorted(entries.items()))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--output', type=Path, default=Path('dlms_reader/app/data/obis-pl.json'))
    args = parser.parse_args()
    result = build(args.pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print('Zapisano wpisów:', len(result['entries']))
