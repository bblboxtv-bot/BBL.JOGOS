"""Run with: python -m unittest discover -s tests -p test_bblia_sync_regression.py"""
import sys
import types
import unittest

try:
    import bblia_sync as sync
except ModuleNotFoundError as exc:
    if exc.name != 'bblia_google':
        raise
    raise


class SyncRegressionTests(unittest.TestCase):
    def test_preferences_preserved_on_equal_timestamp(self):
        a, b = sync.empty(), sync.empty()
        a['preferences'] = {'name': 'Maria'}
        a['preferencesUpdated'] = b['preferencesUpdated'] = 100
        self.assertEqual(sync.merge([a,b])['preferences'], {'name':'Maria'})
        self.assertEqual(sync.merge([b,a])['preferences'], {'name':'Maria'})

    def test_newer_preference_wins(self):
        a, b = sync.empty(), sync.empty()
        a['preferences'], a['preferencesUpdated'] = {'name':'old'}, 100
        b['preferences'], b['preferencesUpdated'] = {'name':'new'}, 101
        for states in ([a,b], [b,a]):
            self.assertEqual(sync.merge(states)['preferences'], {'name':'new'})

    def test_invalid_schema_versions(self):
        for version in (True, 1.0, '1', None):
            with self.subTest(version=version):
                value=sync.empty();value['version']=version
                with self.assertRaises(Exception):sync.validate(value)

    def test_invalid_timestamps_do_not_poison_merge(self):
        for value in (float('nan'),float('inf'),float('-inf'),True,False):
            with self.subTest(value=str(value)):
                self.assertEqual(sync.stamp(value),0)
                state=sync.empty();state['preferencesUpdated']=value
                self.assertEqual(sync.validate(state)['preferencesUpdated'],0)


if __name__=='__main__':unittest.main()
