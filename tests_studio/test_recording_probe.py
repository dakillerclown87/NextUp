import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('recording_probe', Path(__file__).resolve().parents[1]/'tools/recording_probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeTests(unittest.TestCase):
    def test_collect_only_reads_and_excludes_account_device_and_token_fields(self):
        calls = []
        raw = {'id': probe.IDS[0], 'name': 'Stay', 'external_ids': {'isrc': 'TEST'},
               'access_token': 'DO-NOT-EXPORT', 'artists': [{'id': 'artist'}]}
        def get(path):
            calls.append(path)
            return {'item': raw, 'device': {'id': 'SECRET-DEVICE', 'name': 'SECRET-NAME'},
                    'context': {'uri': 'spotify:playlist:PRIVATE'}, 'is_playing': True} if path == 'me/player' else raw
        report = probe.collect(get, {'spotify_device': 'SECRET-DEVICE', 'fallback_playlist': 'PRIVATE', 'spotify_client_id': 'SECRET-CLIENT'})
        self.assertEqual(len(calls), 3)
        self.assertTrue(report['device_matches_saved'])
        self.assertTrue(report['context_matches_saved_playlist'])
        encoded = json.dumps(report)
        for secret in ('DO-NOT-EXPORT', 'SECRET-DEVICE', 'SECRET-NAME', 'SECRET-CLIENT', 'PRIVATE'):
            self.assertNotIn(secret, encoded)

    def test_control_endpoints_rejected_before_network(self):
        with patch('urllib.request.build_opener') as opened:
            for path in ('me/player/play', 'me/player/next', 'me/player/pause', 'https://other.example'):
                with self.assertRaises(probe.ProbeError): probe.spotify_get('secret', path)
            opened.assert_not_called()

