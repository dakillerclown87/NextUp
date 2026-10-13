"""Startup must not initialize optional audio/recognition engines."""
import subprocess
import sys
import unittest
from pathlib import Path


class StartupTests(unittest.TestCase):
    def test_service_construction_defers_audio_engines(self):
        code = '''
import asyncio, sys, tempfile
from pathlib import Path
from aiohttp import ClientSession
from studio.server import Studio
async def check():
    with tempfile.TemporaryDirectory() as home:
        async with ClientSession() as session:
            studio = Studio(session, Path(home))
            try:
                assert 'numpy' not in sys.modules
                assert 'shazamio' not in sys.modules
            finally:
                await studio.cleanup()
asyncio.run(check())
'''
        result = subprocess.run([sys.executable, '-c', code],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
