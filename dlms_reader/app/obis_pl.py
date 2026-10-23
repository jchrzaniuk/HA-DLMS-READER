"""Polskie opisy potwierdzone w opublikowanych tabelach OBIS."""

import json
from functools import lru_cache
from pathlib import Path

DATA = json.loads((Path(__file__).parent / 'data' / 'obis-pl.json').read_text())


@lru_cache(maxsize=16384)
def description(obis):
    try:
        a, b, c, d, e, f = map(int, obis.split('.'))
    except (ValueError, AttributeError):
        return None
    # Pola producenta/dostawcy i niepotwierdzone okresy nie otrzymują nazwy ogólnej.
    if not 0 <= b <= 64 or f != 255:
        return None
    entry = DATA['entries'].get(f'{a}:{c}.{d}.{e}')
    if not entry:
        return None
    source = DATA['sources'][entry['source']]
    text = entry['text'] + (f' — kanał {b}' if b else '')
    return {'text': text, 'source': entry['source'], 'title': source['title'],
            'page': entry['page'], 'url': source['url'] + f'#page={entry["page"]}'}


def localize(item):
    original = item.get('original_name', item.get('name') or item['obis'])
    translated = description(item['obis'])
    return {**item, 'name': translated['text'] if translated else original,
            'original_name': original, 'obis_description': translated}


def source_documents():
    return [{'id': key, **value} for key, value in DATA['sources'].items()]
