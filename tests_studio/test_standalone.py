"""Public-distribution and standalone runtime regressions."""
import asyncio, io, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from aiohttp import ClientSession
from studio.server import Studio
from studio.chat_transport import chat_line
from studio.twitch_service import StudioBot
from tools import release

class StandaloneTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_setup_has_no_accounts_or_other_product_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            async with ClientSession() as session:
                s=Studio(session,home)
                try:
                    state=s.state()
                    self.assertNotIn('cloud',state)
                    self.assertFalse(state['connections']['spotify'])
                    self.assertFalse(state['connections']['twitch'])
                    self.assertEqual(state['settings']['channel'],'')
                    self.assertEqual(state['settings']['spotify_client_id'],'')
                    self.assertEqual(state['queue']['items'],[])
                    self.assertFalse(hasattr(s,'recognizer'))
                    self.assertFalse(hasattr(s,'cloud'))
                finally:await s.cleanup()

    async def test_chat_transport_dispatches_requests_without_recognition(self):
        with tempfile.TemporaryDirectory() as tmp:
            async with ClientSession() as session:
                s=Studio(session,Path(tmp))
                try:
                    s.chat=AsyncMock(return_value=True)
                    bot=StudioBot({'channel':'testchannel'},s.twitch,studio=s)
                    reader=asyncio.StreamReader()
                    reader.feed_data(b'@id=msg1;user-id=42 :viewer!viewer@viewer PRIVMSG #testchannel :!sr https://youtu.be/abcdefghijk\r\n')
                    reader.feed_eof()
                    await bot.receive_loop(reader,AsyncMock(),'bot')
                    await asyncio.gather(*list(bot.work))
                    s.chat.assert_awaited_once()
                    self.assertEqual(s.chat.await_args.args[1],'viewer')
                    self.assertNotIn('songid',sys.modules)
                    self.assertNotIn('songscout',sys.modules)
                finally:await s.cleanup()

    def test_reply_wire_length_and_injection(self):
        wire=chat_line('channel','msg1','Hello\r\nPRIVMSG #other :'+('🎵'*500))
        self.assertLessEqual(len(wire),512)
        self.assertEqual(wire.count(b'\r\n'),1)
        self.assertTrue(wire.startswith(b'@reply-parent-msg-id=msg1 PRIVMSG #channel :'))

    def test_packaging_excludes_personal_files_and_unlisted_root_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            candidates=['README.md','studio/server.py','userdata/accounts.json','studio/accounts.json',
                'studio/overlay-key.txt','docs/private-key.txt','studio/queue.sqlite3','studio/tokens.json',
                'studio/.env','studio/secret.pfx','my-private-notes.txt','build/private.py','songid/server.py']
            for name in candidates:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('test')
            with patch.object(release,'ROOT',root):included={rel.as_posix() for _,rel in release.files()}
            self.assertEqual(included,{'README.md','studio/server.py'})

    def test_default_home_is_new_and_does_not_adopt_legacy_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            old=Path(tmp)/'SongScout/userdata';old.mkdir(parents=True)
            (old/'accounts.json').write_text('{"private":"sentinel"}')
            env={k:v for k,v in os.environ.items() if k not in ('NEXTUP_HOME','SONGSCOUT_HOME')}
            env['LOCALAPPDATA']=tmp
            code='import sys; sys.path.insert(0, '+repr(str(Path(__file__).resolve().parents[1]))+'); from studio.settings import HOME; import bootstrap; print(HOME); print(bootstrap.HOME)'
            result=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,check=True)
            self.assertEqual(result.stdout.splitlines(),[str(Path(tmp)/'NextUp')]*2)
            self.assertFalse((Path(tmp)/'NextUp/userdata/accounts.json').exists())

    def test_installer_activation_preserves_existing_user_credentials_and_settings(self):
        import importlib.util
        import bootstrap
        spec=importlib.util.spec_from_file_location('nextup_install_test',Path(__file__).resolve().parents[1]/'packaging/windows/install_support.py')
        support=importlib.util.module_from_spec(spec)
        old_path=list(sys.path)
        try:
            spec.loader.exec_module(support)
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);data=root/'userdata';data.mkdir()
                sentinels={'accounts.json':b'{"fixture_token":"keep-local-only"}', 'studio.json':b'{"theme":"dark"}', 'queue.sqlite3':b'fixture-queue-bytes'}
                for name,value in sentinels.items():(data/name).write_bytes(value)
                old='2.0.0-beta.1';new='2.0.0-beta.2'
                (root/'versions'/old/'runtime').mkdir(parents=True)
                (root/'versions'/old/'runtime/python.exe').touch()
                (root/'versions'/new).mkdir()
                (root/'current.json').write_text(json.dumps({'version':old}))
                with patch.object(support,'root',root),patch.object(bootstrap,'HOME',root),patch.object(support.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'Preflight passed','')):
                    support.activate(new)
                self.assertEqual(json.loads((root/'current.json').read_text())['version'],new)
                self.assertEqual(json.loads((root/'previous.json').read_text())['version'],old)
                for name,value in sentinels.items():self.assertEqual((data/name).read_bytes(),value)
        finally:sys.path[:]=old_path
