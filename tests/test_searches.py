from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from server.cache import connect
from server.library import Library
from server.searches import Searches, parse_query
from server.semantic import Encoder


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.library = Library(root, root / 'cache', Encoder(root / 'models'))
        self.ids = [f'{number:064x}' for number in range(1, 4)]
        with connect(self.library.directory) as db:
            for image_id, path, camera, date in zip(self.ids, ['trips/beach sunset.jpg', "John's 100%.png", 'mountain.jpg'], ['Canon EOS', None, 'Nikon'], ['2020-06-15', '2026-01-01', '2020-01-01']):
                db.execute('INSERT INTO images VALUES (?,?,?,?,?,?,?)', (image_id, 32, 24, 'image/png' if path.endswith('png') else 'image/jpeg', 100, date + 'T12:00:00Z', camera))
                db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?)', (path, path.rpartition('/')[0], image_id, 100, 0, date + 'T12:00:00Z', None))
        self.filters = {'folder': '', 'type': '', 'range': 'all', 'from': '', 'to': ''}

    def test_operators_combine_with_existing_filters_and_metadata_only_needs_no_model(self):
        result = self.library.pictures({'q': 'year:2020 camera:"Canon EOS" type:jpg', 'mode': 'hybrid'})
        self.assertEqual([row['id'] for row in result['items']], [self.ids[0]])
        self.assertEqual(self.library.pictures({'q': 'year:2020', 'from': '2026-01-01', 'mode': 'hybrid'})['total'], 0)
        self.assertEqual(self.library.pictures({'q': 'name:"beach sunset.jpg" folder:trips'})['total'], 1)
        self.assertEqual(self.library.pictures({'q': 'from:2020-01-01 to:2020-12-31'})['total'], 2)

    def test_plain_queries_keep_apostrophes_and_literal_wildcards(self):
        self.assertEqual(parse_query("John's 100%"), ("John's 100%", {}))
        self.assertEqual(self.library.pictures({'q': "John's 100%", 'mode': 'hybrid'})['items'][0]['id'], self.ids[1])
        suggestion = self.library.searches.suggestions("John's")[0]['query']
        self.assertEqual(self.library.pictures({'q': suggestion})['items'][0]['id'], self.ids[1])

    def test_invalid_operators_are_explained(self):
        for query in ('year:20', 'year:0000', 'year:2020 from:2020-01-01', 'type:exe', 'camera:', 'camera:"unfinished', 'from:2020-02-30'):
            with self.subTest(query=query), self.assertRaises(ValueError):
                self.library.pictures({'q': query})

    def test_hybrid_combines_candidates_and_has_stable_pagination(self):
        self.library.semantic = SimpleNamespace(status=lambda: {'indexed': 3}, search=lambda **kwargs: [(self.ids[2], .3), (self.ids[0], .2)])
        results = self.library.pictures({'q': 'beach', 'mode': 'hybrid'})
        self.assertEqual([row['id'] for row in results['items']], [self.ids[0], self.ids[2]])
        self.assertEqual(self.library.pictures({'q': 'beach', 'mode': 'hybrid', 'folder': 'trips'})['total'], 1)
        pages = [self.library.pictures({'q': 'beach', 'mode': 'hybrid', 'limit': '1', 'offset': str(n)})['items'][0]['id'] for n in range(2)]
        self.assertEqual(pages, [self.ids[0], self.ids[2]])

    def test_suggestions_come_from_indexed_values(self):
        self.assertEqual(self.library.searches.suggestions('camera:Can')[0]['query'], 'camera:"Canon EOS"')
        self.assertEqual(self.library.searches.suggestions('year:2020')[0]['query'], 'year:2020')
        self.assertEqual(self.library.searches.suggestions('beach')[0]['label'], 'beach sunset.jpg')
        self.assertEqual(self.library.searches.suggestions('x'), [])

    def test_saved_search_persists_and_removes_without_changing_index(self):
        values = {'action': 'save', 'name': 'Beach trips', 'query': 'beach year:2020', 'mode': 'hybrid', 'sort': 'newest', 'filters': self.filters}
        saved = self.library.searches.update(values)[0]
        reopened = Searches(self.library)
        self.assertEqual(reopened.list(), [saved])
        with self.assertRaisesRegex(ValueError, 'already used'):
            reopened.update(values)
        self.assertEqual(reopened.update({'action': 'remove', 'id': saved['id']}), [])
        self.assertEqual(self.library.pictures({})['total'], 3)

    def test_bad_saved_queries_are_rejected(self):
        values = {'action': 'save', 'name': 'Search', 'query': 'beach', 'mode': 'hybrid', 'sort': 'newest', 'filters': self.filters}
        for change in ({'mode': 'remote'}, {'name': ''}, {'filters': {}}, {'query': 'year:0'}, {'sort': 'unsafe'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.library.searches.update({**values, **change})
        self.assertEqual(self.library.searches.list(), [])
