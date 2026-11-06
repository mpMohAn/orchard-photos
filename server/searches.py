"""Local query operators, indexed suggestions, and per-workspace saved searches."""
from datetime import datetime
import json
import re
import secrets
import shlex

from server.cache import connect

MODES = {'name', 'visual', 'hybrid'}
SORTS = {'newest', 'oldest', 'name-asc', 'name-desc', 'size-asc', 'size-desc'}
TYPES = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'heic': 'image/heif', 'heif': 'image/heif',
         'webp': 'image/webp', 'gif': 'image/gif', 'tiff': 'image/tiff', 'tif': 'image/tiff', 'bmp': 'image/bmp', 'avif': 'image/avif'}


def like(text):
    return '%' + text.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'


def parse_query(query):
    """Recognized operators become additional filters. Ordinary words remain a text query."""
    if not re.search(r'(^|\s)(from|to|year|camera|name|folder|type):', query):
        return query.strip(), {}
    try:
        lexer = shlex.shlex(query, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = ''
        lexer.quotes = '\"'
        tokens = list(lexer)
    except ValueError:
        raise ValueError('Close the quotation marks in your search.') from None
    words, filters = [], {}
    for token in tokens:
        key, separator, value = token.partition(':')
        if not separator or key not in {'from', 'to', 'year', 'camera', 'name', 'folder', 'type'}:
            words.append(token)
            continue
        if not value or key in filters:
            raise ValueError(f'Use one non-empty {key}: filter.')
        filters[key] = value
    year = filters.pop('year', '')
    if year:
        if not re.fullmatch(r'[0-9]{4}', year) or not 1 <= int(year) <= 9999:
            raise ValueError('Use a four-digit year.')
        if 'from' in filters or 'to' in filters:
            raise ValueError('Use year: or a from:/to: range in one search.')
        filters.update({'from': f'{year}-01-01', 'to': f'{year}-12-31'})
    if 'type' in filters:
        kind = filters['type'].lower().removeprefix('.')
        if kind not in TYPES and kind not in TYPES.values():
            raise ValueError('Use a supported image type, such as type:jpg or type:png.')
        filters['type'] = TYPES.get(kind, kind)
    return ' '.join(words), filters


class Searches:
    def __init__(self, library):
        self.library = library
        with connect(library.directory) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS saved_searches (
                id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, payload TEXT NOT NULL
            )''')

    def list(self):
        with connect(self.library.directory, rows=True) as db:
            return [{'id': row['id'], 'name': row['name'], **json.loads(row['payload'])}
                    for row in db.execute('SELECT * FROM saved_searches ORDER BY name COLLATE NOCASE,id')]

    def update(self, values):
        action = values.get('action')
        if action == 'remove':
            if not isinstance(values.get('id'), str):
                raise ValueError('Choose a saved search.')
            with connect(self.library.directory) as db:
                db.execute('DELETE FROM saved_searches WHERE id=?', (values['id'],))
            return self.list()
        if action != 'save':
            raise ValueError('Choose save or remove.')
        name, query = values.get('name'), values.get('query')
        mode, order, filters = values.get('mode'), values.get('sort'), values.get('filters')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or not isinstance(query, str) or len(query) > 1000:
            raise ValueError('Use a search name of 1–80 characters and a query of up to 1,000 characters.')
        if not isinstance(mode, str) or mode not in MODES or not isinstance(order, str) or order not in SORTS:
            raise ValueError('Choose a supported search mode and order.')
        if not isinstance(filters, dict) or set(filters) != {'folder', 'type', 'range', 'from', 'to'} or any(not isinstance(value, str) or len(value) > 1000 for value in filters.values()):
            raise ValueError('Use valid saved filters.')
        if filters['range'] not in {'all', 'today', '7d', '28d', 'year', 'custom'}:
            raise ValueError('Choose a supported date range.')
        for key in ('from', 'to'):
            if filters[key]:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', filters[key]):
                    raise ValueError('Use valid dates in saved filters.')
                try:
                    datetime.strptime(filters[key], '%Y-%m-%d')
                except ValueError:
                    raise ValueError('Use valid dates in saved filters.') from None
        if filters['from'] and filters['to'] and filters['from'] > filters['to']:
            raise ValueError('The end date must follow the start date.')
        text, operators = parse_query(query)
        self.library.filters(operators)
        if not text and not operators and not any(filters[key] for key in ('folder', 'type')) and filters['range'] == 'all':
            raise ValueError('Enter a search or choose filters before saving.')
        payload = {'query': query, 'mode': mode, 'sort': order, 'filters': filters}
        with connect(self.library.directory) as db:
            if db.execute('SELECT count(*) FROM saved_searches').fetchone()[0] >= 100:
                raise ValueError('This workspace already has 100 saved searches.')
            if db.execute('SELECT 1 FROM saved_searches WHERE name=? COLLATE NOCASE', (name.strip(),)).fetchone():
                raise ValueError('That search name is already used. Choose another name.')
            db.execute('INSERT INTO saved_searches VALUES (?,?,?)', (secrets.token_hex(8), name.strip(), json.dumps(payload)))
        return self.list()

    def suggestions(self, query):
        query = query.strip()[:200]
        if len(query) < 2:
            return []
        result = []
        with connect(self.library.directory, rows=True) as db:
            if query.startswith('camera:'):
                values = db.execute("SELECT DISTINCT camera FROM images WHERE camera IS NOT NULL AND camera LIKE ? ESCAPE '!' ORDER BY camera LIMIT 8", (like(query[7:]),))
                return [{'query': 'camera:' + json.dumps(row[0], ensure_ascii=False), 'label': row[0], 'kind': 'camera'} for row in values]
            if query.startswith('year:') or query.isdigit():
                prefix = query.removeprefix('year:')
                values = db.execute('''SELECT DISTINCT substr(coalesce(i.taken,f.modified),1,4) AS year
                                       FROM files f JOIN images i ON i.id=f.image_id WHERE year LIKE ? ORDER BY year DESC LIMIT 8''', (prefix + '%',))
                return [{'query': 'year:' + row[0], 'label': row[0], 'kind': 'year'} for row in values]
            values = db.execute("SELECT DISTINCT path FROM files WHERE image_id IS NOT NULL AND path LIKE ? ESCAPE '!' ORDER BY path LIMIT 32", (like(query),))
            seen = set()
            for row in values:
                name = row[0].rsplit('/', 1)[-1]
                if name not in seen:
                    result.append({'query': 'name:' + json.dumps(name, ensure_ascii=False), 'label': name, 'kind': 'filename'})
                    seen.add(name)
                if len(result) == 8:
                    break
        return result
