"""Local test fixture only: fake provider metadata, real Studio HTTP/WebSocket server."""
import asyncio
import studio.server as server
original = server.Studio

def create(*a, **k):
    s = original(*a, **k)
    s.settings.save({'youtube_player_mode': 'chrome', 'block_explicit': False})
    async def resolve(ident):
        return {'provider':'youtube','id':ident,'title':'Browser test song','artists':['Test artist'],
                'artist_ids':['test'],'duration':30,'explicit':False,
                'url':'https://www.youtube.com/watch?v='+ident,'art':''}
    s.youtube.resolve = resolve
    # Exercise the real Spotify adapter, with a paused device that became idle
    # while YouTube played. No network or account credentials are used.
    s.spotify.remember_device({'device': {'id': 'test-pc'}})
    player = {'device': {'id': 'test-pc'}, 'is_playing': False,
              'item': None, 'repeat_state': 'off'}
    async def spotify_api(method, path, **kwargs):
        if path == 'me/player/devices':
            return {'devices': [{'id': 'test-pc', 'is_active': False}]}
        if method == 'PUT' and path == 'me/player/play':
            assert kwargs['params']['device_id'] == 'test-pc'
            player.update(is_playing=True, item={'id': kwargs['json']['uris'][0].split(':')[-1]})
        elif method == 'PUT' and path == 'me/player/pause':
            player['is_playing'] = False
        return dict(player) if method == 'GET' else {}
    async def spotify_resolve(ident):
        item = await resolve(ident)
        return {**item, 'provider': 'spotify', 'title': 'Spotify handoff test',
                'url': 'https://open.spotify.com/track/' + ident}
    s.spotify.api = spotify_api
    s.spotify.resolve = spotify_resolve
    return s

server.Studio = create
asyncio.run(server.run(open_browser=False))
