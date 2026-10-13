"""Reward ownership, renamed IDs, live recovery and per-role request methods."""
import asyncio, copy, json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from aiohttp import ClientSession
from aiohttp.test_utils import TestClient, TestServer
from studio.server import Studio, admin_app
from studio.providers import ServiceError
from studio.settings import Settings
from test_core import track

class Socket:
    def __init__(self):self.inbox=asyncio.Queue();self.closed=False
    def feed(self,kind,payload):self.inbox.put_nowait(SimpleNamespace(type=SimpleNamespace(name='TEXT'),data=json.dumps({'metadata':{'message_type':kind},'payload':payload})))
    async def receive(self):return await self.inbox.get()
    async def close(self):self.closed=True

class RewardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.session=ClientSession();self.s=Studio(self.session,Path(self.tmp.name));self.t=self.s.twitch
        self.t.prepare=AsyncMock();self.t.identity={'user_id':'100'};self.t.broadcaster='100'
        self.t.roles=AsyncMock(return_value=['viewer']);self.s.spotify.resolve=AsyncMock(return_value=track())
        self.external={'id':'external','title':'My SongRequest','cost':100,'is_user_input_required':True,'is_enabled':True,'is_paused':False,'should_redemptions_skip_request_queue':False}
        self.owned={**self.external,'id':'owned','title':'NextUp SongRequest'}
        self.no_input={**self.external,'id':'no-input','is_user_input_required':False}
        self.calls=[];self.history_error=False;self.subscribed=asyncio.Event();self.task=None
        self.t.api=self.api
        self.client=TestClient(TestServer(admin_app(self.s)));await self.client.start_server()
        self.headers={'Host':'127.0.0.1:8888','X-NextUp-Key':self.s.admin}
    async def asyncTearDown(self):
        if self.task:self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        self.s.bot=None
        await self.client.close();await self.s.cleanup();await self.session.close()
        self.tmp.cleanup()
    async def api(self,method,path,**kwargs):
        self.calls.append((method,path,kwargs))
        if path=='channel_points/custom_rewards':
            if method=='GET':return {'data':[self.owned] if kwargs['params'].get('only_manageable_rewards')=='true' else [self.external,self.owned,self.no_input]}
            return {'data':[{**self.owned,**kwargs['json']}]}
        if path=='channel_points/custom_rewards/redemptions':
            if self.history_error:
                error=ServiceError('Not owned');error.status=403;raise error
            return {'data':[]}
        if path=='eventsub/subscriptions':self.subscribed.set();return {'data':[{'id':'sub'}]}
        raise AssertionError((method,path))
    def event(self,reward='external',rid='redemption',title='Renamed on Twitch'):
        return {'id':rid,'reward':{'id':reward,'title':title},'user_id':rid,'user_login':'viewer','user_input':'https://open.spotify.com/track/'+'a'*22,'status':'unfulfilled'}
    async def listen(self,reward):
        self.s.settings.save({'reward_id':reward,'points_enabled':True})
        self.ws=Socket();self.t.session=Mock(ws_connect=AsyncMock(return_value=self.ws));self.handled=asyncio.Event()
        async def consume(event):await self.s.redemption(event);self.handled.set()
        self.task=asyncio.create_task(self.t.points(consume));self.ws.feed('session_welcome',{'session':{'id':'session'}})
        await asyncio.wait_for(self.subscribed.wait(),2)
    async def test_creation_name_and_cost(self):
        await self.t.create_reward();self.assertEqual(self.calls[-1][2]['json']['title'],'NextUp SongRequest')
        await self.t.create_reward('SongRequest',750);self.assertEqual(self.calls[-1][2]['json']['title'],'SongRequest');self.assertEqual(self.calls[-1][2]['json']['cost'],750)
        with self.assertRaises(ValueError):await self.t.create_reward('',1)
    async def test_picker_lists_external_and_validates_text_input(self):
        r=await self.client.post('/api/rewards',headers=self.headers,json={});rows=(await r.json())['rewards']
        self.assertFalse(rows[0]['manageable']);self.assertTrue(rows[1]['manageable'])
        r=await self.client.post('/api/settings',headers=self.headers,json={'reward_id':'external'});self.assertEqual(r.status,200)
        self.external['title']='Renamed';await self.t.list_rewards();self.assertEqual(self.t.selected_reward['title'],'Renamed');self.assertEqual(self.s.settings.value['reward_id'],'external')
        r=await self.client.post('/api/settings',headers=self.headers,json={'reward_id':'no-input'});self.assertEqual(r.status,400);self.assertEqual(self.s.settings.value['reward_id'],'external')
    async def test_external_live_requests_without_history_access_and_manual_refund(self):
        await self.listen('external');event=self.event();self.ws.feed('notification',{'event':event});await asyncio.wait_for(self.handled.wait(),2)
        self.assertEqual(len(self.s.queue.state['items']),1);self.assertFalse(any(p.endswith('/redemptions') for m,p,k in self.calls));self.assertEqual(self.t.points_status,'Connected')
        await self.s.redemption({**event,'reward':{'id':'external','title':'Renamed again'}});self.assertEqual(len(self.s.queue.state['items']),1)
        self.s.queue.remove(self.s.queue.state['items'][0]['id']);row=self.s.queue.state['settlements'][0];self.assertTrue(row['manual']);self.assertTrue(row['done'])
    async def test_history_failure_does_not_disconnect_eventsub(self):
        self.history_error=True;await self.listen('owned');self.ws.feed('notification',{'event':self.event('owned')});await asyncio.wait_for(self.handled.wait(),2)
        self.assertEqual(self.t.points_status,'Connected');self.assertEqual(len(self.s.queue.state['items']),1);self.assertFalse(self.task.done())
    async def test_rename_uses_id_and_other_rewards_are_ignored(self):
        self.s.settings.save({'reward_id':'owned'});self.t.selected_reward=await self.t.validate_reward('owned')
        await self.s.redemption(self.event('owned',title='SongRequest'));await self.s.redemption(self.event('other','other',title='SongRequest'))
        self.assertEqual(len(self.s.queue.state['items']),1);self.assertEqual(self.t.selected_reward['title'],'SongRequest')
        self.s.queue.remove(self.s.queue.state['items'][0]['id']);self.assertFalse(self.s.queue.state['settlements'][0]['done'])
    async def test_fulfilled_event_not_settled_twice(self):
        self.s.settings.save({'reward_id':'owned'});self.t.selected_reward=await self.t.validate_reward('owned')
        await self.s.redemption({**self.event('owned'),'status':'fulfilled'});self.s.queue.remove(self.s.queue.state['items'][0]['id'])
        row=self.s.queue.state['settlements'][0];self.assertTrue(row['done']);self.assertFalse(row['manual'])
    async def test_viewer_command_blocked_before_lookup_but_tier_allowed(self):
        self.s.settings.value['roles']['viewer']['request_method']='points';self.s.settings.save({'reward_id':'external','points_enabled':True});self.s.bot=Mock()
        await self.s.chat('10','viewer','chat-a','!sr https://open.spotify.com/track/'+'a'*22,{})
        self.s.spotify.resolve.assert_not_awaited();self.assertIn('channel-point',self.s.bot.reply.call_args.args[1])
        self.t.roles=AsyncMock(return_value=['viewer','tier1','tier2'])
        await self.s.chat('20','subscriber','chat-b','!sr https://open.spotify.com/track/'+'a'*22,{})
        self.assertEqual(len(self.s.queue.state['items']),1);self.assertIn('Queued',self.s.bot.reply.call_args.args[1])
    async def test_request_method_matrix_and_role_precedence(self):
        for method in ('both','points','chat','disabled'):
            self.s.settings.value['roles']['viewer']['request_method']=method
            for points in (False,True):
                if method=='both' or method==('points' if points else 'chat'):self.s.queue.check_request_method(['viewer'],points)
                else:
                    with self.assertRaises(ValueError):self.s.queue.check_request_method(['viewer'],points)
                self.s.queue.check_request_method(['viewer'],points,owner=True)
        self.s.settings.value['roles']['viewer']['request_method']='points';self.s.settings.value['roles']['tier2']['request_method']='chat';self.s.settings.value['roles']['mod']['request_method']='disabled'
        self.s.queue.check_request_method(['viewer','tier1','tier2'],False)
        with self.assertRaises(ValueError):self.s.queue.check_request_method(['viewer','tier2','mod'],False)
    async def test_chat_only_role_redemption_rejected_and_refunded(self):
        self.s.settings.save({'reward_id':'owned'});self.t.selected_reward=await self.t.validate_reward('owned');self.s.settings.value['roles']['viewer']['request_method']='chat'
        await self.s.redemption(self.event('owned'));self.s.spotify.resolve.assert_not_awaited();self.assertFalse(self.s.queue.state['items']);row=self.s.queue.state['settlements'][0];self.assertEqual(row['status'],'CANCELED');self.assertFalse(row['done'])
    async def test_legacy_migration_and_policy_persistence(self):
        roles=copy.deepcopy(self.s.settings.value['roles'])
        for role in roles.values():role.pop('request_method')
        self.s.settings.save({'roles':roles});self.assertTrue(all(r['request_method']=='both' for r in self.s.settings.value['roles'].values()))
        roles=self.s.settings.value['roles'];roles['viewer']['request_method']='points';self.s.settings.save({'roles':roles})
        self.assertEqual(Settings(self.s.settings.path).value['roles']['viewer']['request_method'],'points')
