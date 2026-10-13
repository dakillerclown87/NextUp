import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestClient, TestServer
from studio.server import Studio
from studio.moderation import Moderation
from studio.queue import Queue
from studio.reply_pool import choose_reply
from studio.settings import Settings, validate


def track(ident='a', explicit=False):
    return {'id':ident,'provider':'spotify','title':'Song '+ident,'artists':['Artist'],
            'artist_ids':[],'duration':200,'explicit':explicit,'url':'https://open.spotify.com/track/'+ident}


class ReplyTests(unittest.TestCase):
    def test_shuffle_survives_restart_and_does_not_repeat_at_cycle_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings=Settings(Path(tmp)/'settings.json')
            q=Queue(Path(tmp)/'q.db',settings)
            command={'name':'!hello','reply':'One\nTwo\nThree\nFour'}
            seen=[choose_reply(q,command)]
            q.db.close();q=Queue(Path(tmp)/'q.db',settings)
            seen += [choose_reply(q,command) for _ in range(3)]
            self.assertEqual(set(seen),{'One','Two','Three','Four'})
            self.assertNotEqual(choose_reply(q,command),seen[-1])
            command['reply']='Updated';self.assertEqual(choose_reply(q,command),'Updated')
            q.db.close()

    def test_custom_command_count_has_no_product_cap_and_fun_names_available(self):
        rows=[{'name':'!c'+str(i),'reply':'A\nB','permission':'everyone','cooldown':0,'enabled':True} for i in range(150)]
        rows.append({**rows[0],'name':'!roast'})
        self.assertEqual(len(validate({'custom_commands':rows})['custom_commands']),151)
        old=validate({})['roles'];old['viewer']['priority']=99
        self.assertNotIn('priority',validate({'roles':old})['roles']['viewer'])


class ModerationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.session=ClientSession()
        self.s=Studio(self.session,Path(self.temp.name))
        self.s.settings.save({'moderators_enabled':True,'require_approval':True})
        self.client=TestClient(TestServer(self.s.moderation.application()))
        await self.client.start_server()
        self.s.spotify.pause=AsyncMock()

    async def asyncTearDown(self):
        await self.client.close();await self.s.cleanup();await self.session.close();self.temp.cleanup()

    async def pair(self,name='Mod',**permissions):
        code=self.s.moderation.create({'name':name,**permissions})
        r=await self.client.post('/pair',json={'code':code['code']})
        self.assertEqual(r.status,200)
        return code,{'Authorization':'Bearer '+(await r.json())['token']}

    def add(self,ident='a',**kw):
        return self.s.queue.add(track(ident,**kw),{'id':ident,'login':ident},['viewer'])

    async def test_multiple_moderators_scoped_permissions_and_revocation(self):
        a,ha=await self.pair('Approve only',reject=False)
        b,hb=await self.pair('Reject only',approve=False)
        item=self.add()
        r=await self.client.get('/requests',headers=ha);body=await r.json()
        self.assertEqual(body['items'][0]['id'],item['id'])
        self.assertNotIn('settings',body)
        self.assertEqual((await self.client.post('/review',headers=hb,json={'id':item['id'],'action':'approve'})).status,403)
        self.assertEqual((await self.client.post('/review',headers=ha,json={'id':item['id'],'action':'approve'})).status,200)
        self.assertEqual(item['status'],'queued')
        self.assertEqual((await self.client.post('/review',headers=ha,json={'id':item['id'],'action':'approve'})).status,400)
        self.s.moderation.revoke(a['id'])
        self.assertEqual((await self.client.get('/requests',headers=ha)).status,401)
        self.assertEqual((await self.client.get('/requests',headers=hb)).status,200)
        self.s.moderation=Moderation(self.s)
        self.assertEqual(len(self.s.moderation.members),1)
        stored=self.s.moderation.path.read_text();self.assertNotIn(hb['Authorization'].removeprefix('Bearer '),stored)

    async def test_expiry_one_use_disabled_origin_and_no_admin_routes(self):
        code,headers=await self.pair()
        self.assertEqual((await self.client.post('/pair',json={'code':code['code']})).status,400)
        expired=self.s.moderation.create({'name':'Expired'})
        self.s.moderation.pending[expired['id']]['expires']=0
        self.assertEqual((await self.client.post('/pair',json={'code':expired['code']})).status,400)
        self.assertEqual((await self.client.get('/requests')).status,401)
        self.assertEqual((await self.client.get('/requests',headers={**headers,'Origin':'https://evil.example'})).status,403)
        for path in ('/api/state','/api/settings','/static/app.js','/callback/spotify','/accounts.json'):
            self.assertEqual((await self.client.get(path,headers=headers)).status,404)
        self.s.settings.save({'moderators_enabled':False})
        self.assertEqual((await self.client.get('/requests',headers=headers)).status,403)

    async def test_policy_blocks_approval_and_rejection_refunds_points(self):
        _,headers=await self.pair()
        item=self.add()
        self.s.settings.save({'max_seconds':30})
        self.assertEqual((await self.client.post('/review',headers=headers,json={'id':item['id'],'action':'approve'})).status,400)
        self.assertEqual(item['status'],'review')
        item['redemption']={'id':'reward1','reward':'r','broadcaster':'b'}
        self.assertEqual((await self.client.post('/review',headers=headers,json={'id':item['id'],'action':'reject'})).status,200)
        self.assertEqual(self.s.queue.state['settlements'][0]['status'],'CANCELED')

    async def test_pair_attempts_throttled(self):
        for _ in range(12):
            self.assertEqual((await self.client.post('/pair',json={'code':'bad'})).status,400)
        self.assertEqual((await self.client.post('/pair',json={'code':'bad'})).status,429)

    async def test_live_queue_current_and_playlist_are_scoped_and_updated(self):
        _, headers = await self.pair()
        review = self.add('pending')
        queued = self.add('upnext'); self.s.queue.approve(queued['id'])
        current = self.add('current'); self.s.queue.approve(current['id']); self.s.queue.activate(current)
        self.s.settings.save({'fallback_playlist':'A'*22})
        self.s.conductor.fallback.cached_key=('spotify','A'*22,'private-client-id')
        self.s.conductor.fallback.tracks=[{**track('playlist'),'private_field':'hidden'}]
        body=await (await self.client.get('/requests',headers=headers)).json()
        self.assertEqual(body['current']['id'],current['id'])
        self.assertEqual([x['id'] for x in body['queue']],[review['id'],queued['id']])
        self.assertEqual(body['items'][0]['id'],review['id'])
        self.assertTrue(body['playlist']['loaded'])
        self.assertNotIn('private_field',body['playlist']['tracks'][0])
        self.assertNotIn('private-client-id',json.dumps(body))
        await self.client.post('/review',headers=headers,json={'id':review['id'],'action':'approve'})
        another=self.add('later')
        body=await (await self.client.get('/requests',headers=headers)).json()
        self.assertEqual([x['id'] for x in body['items']],[another['id']])
        self.assertEqual(body['queue'][0]['status'],'queued')
        self.s.conductor.fallback.invalidate()
        body=await (await self.client.get('/requests',headers=headers)).json()
        self.assertFalse(body['playlist']['loaded']);self.assertEqual(body['playlist']['tracks'],[])
