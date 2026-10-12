/* Small inline vectors keep the launcher crisp at any Windows display scale. */
function uiIcon(name, cls='') {
  const paths = {
    home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-8H9v8H4a1 1 0 0 1-1-1z"/>',
    queue:'<path d="M9 5h12M9 12h12M9 19h12"/><circle cx="3" cy="5" r=".8"/><circle cx="3" cy="12" r=".8"/><circle cx="3" cy="19" r=".8"/>',
    rewards:'<path d="M3 8h18v5H3zM5 13v8h14v-8M12 8v13"/><path d="M12 8C3 9 5 1 9 3c2 1 3 5 3 5s1-4 3-5c4-2 6 6-3 5Z"/>',
    settings:'<path d="m9 3-1 3-3 1v3l-2 2 2 2v3l3 1 1 3h6l1-3 3-1v-3l2-2-2-2V7l-3-1-1-3z"/><circle cx="12" cy="12" r="3"/>',
    playlists:'<path d="M4 5h11M4 10h9M4 15h6M17 10v10M17 10l4-1v5"/><ellipse cx="14" cy="20" rx="3" ry="2"/>',
    rules:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6"/>',
    commands:'<path d="m5 5 6 7-6 7M13 19h7"/>',
    connections:'<path d="m8 13-2 2a4 4 0 0 0 6 6l4-4a4 4 0 0 0 0-6M16 11l2-2a4 4 0 0 0-6-6L8 7a4 4 0 0 0 0 6M9 15l6-6"/>',
    widgets:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10"/>',
    cloud:'<path d="M6 18a5 5 0 0 1-1-10 7 7 0 0 1 13-1 5.5 5.5 0 0 1 0 11Z"/>',
    diagnostics:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    updates:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    sparkle:'<path d="m10 3 2.5 6.5L19 12l-6.5 2.5L10 21l-2.5-6.5L1 12l6.5-2.5ZM20 2v6m-3-3h6"/>',
    next:'<path d="m5 5 10 7L5 19Z" fill="currentColor" stroke="none"/><path d="M19 5v14" stroke-width="3"/>',
    popout:'<path d="M14 3h7v7M21 3l-9 9M10 5H4v15h15v-6"/>',
    youtube:'<rect x="2" y="5" width="20" height="14" rx="4"/><path d="m10 9 5 3-5 3Z" fill="currentColor" stroke="none"/>',
    twitch:'<path d="M4 3h17v12l-5 5h-5l-4 3v-3H3V7Z"/><path d="M10 7v6M16 7v6"/>',
    spotify:'<circle cx="12" cy="12" r="10" fill="currentColor" stroke="none"/><g stroke="var(--sidebar)" stroke-width="1.6"><path d="M5.5 9c4-2 9-1.8 13 .5M6.5 12.5c3.5-1.5 7.5-1.3 11 .5M7.5 16c3-1 6-1 9 .5"/></g>',
    up:'<path d="m6 13 6-6 6 6M12 7v13"/>',
    menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
    arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
  };
  return `<svg class="ui-icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${paths[name]||paths.settings}</svg>`;
}
function youtubeConnection(){
  const c=state.connections,browser=state.settings.youtube_player_mode==='chrome';
  const connected=!!c.youtube_player&&(!browser||!!c.chrome_connected);
  const label=connected?'Connected':browser?(c.chrome_connected?'Waiting for tab':c.chrome_paired?'Offline':'Not paired'):'Player closed';
  const detail=connected?(browser?'Selected browser tab is responding':'Embedded player is responding'):browser?(c.chrome_connected?'Select a YouTube tab in the NextUp extension':c.chrome_paired?'Open your browser and reconnect the NextUp extension':'Pair the NextUp browser extension in Integrations'):'Open the YouTube player and enable playback';
  return {connected,label,detail,waiting:browser&&!!c.chrome_connected&&!connected};
}
function sidebarStatus(){
  syncNavOverflow();
  for(const provider of ['spotify','youtube','twitch']){
    const el=document.querySelector('[data-service="'+provider+'"]');if(!el)continue;
    const status=provider==='youtube'?youtubeConnection():{connected:!!state.connections[provider],label:state.connections[provider]?'Connected':'Not connected',detail:'Open integrations'};
    el.dataset.connected=String(status.connected);el.dataset.waiting=String(!!status.waiting);
    el.querySelector('small').textContent=status.label;
    el.title=({spotify:'Spotify',youtube:'YouTube',twitch:'Twitch'})[provider]+': '+status.label+' · '+status.detail;
    el.setAttribute('aria-label',el.title);
  }
}
function homeQueueRow(item,index){
  const t=item.track,sent=!!item.spotify_delivery;
  return `<div class="request-card" draggable="${!sent}" data-queue-id="${esc(item.id)}"><span class="queue-position">${index+1}</span>${art(t)}<div class="request-copy"><a href="${esc(t.url)}" target="_blank" rel="noopener noreferrer" title="${esc(t.title)}">${esc(t.title)}</a><span class="request-artist">${esc(t.artists.join(', '))}</span><span class="request-user">${uiIcon('twitch')}<span>${esc(item.user.login)}</span><em class="request-platform">${t.provider==='youtube'?'YouTube':'Spotify'}${item.status==='review'?' · Review':''}${sent?' · Sent':''}</em></span></div><span class="request-duration">${time(t.duration)}</span><button class="icon-button queue-promote" ${index===0||sent?'disabled':''} data-move="${index}" data-dir="-1" title="Move request up" aria-label="Move ${esc(t.title)} up">${uiIcon('up')}</button></div>`;
}
let twitchRewards=[];
function rewardOptions(){const selected=state.settings.reward_id,known=twitchRewards.some(r=>r.id===selected),saved=state.points?.reward;return `<option value="">Choose a Twitch reward</option>${selected&&!known?`<option value="${esc(selected)}" selected>${esc(saved?.id===selected?saved.title:'Saved reward · refresh to see its name')}</option>`:''}${twitchRewards.map(r=>`<option value="${esc(r.id)}" ${r.id===selected?'selected':''} ${!r.is_user_input_required?'disabled':''}>${esc(r.title)} · ${r.cost} points${!r.is_user_input_required?' · text input required':''}</option>`).join('')}`;}
function rewardHelp(r){if(!r)return 'Refresh rewards to choose one created on Twitch or in NextUp. Renaming it on Twitch keeps the same connection.';return (r.manageable?'NextUp can automatically fulfill and refund this reward.':'Twitch-created reward: live requests work while the bot is connected. Complete/refund redemptions in Twitch; offline redemption history is unavailable.')+(!r.is_enabled?' This reward is disabled on Twitch.':'')+(r.is_paused?' This reward is paused on Twitch.':'');}
function rewards(){const c=state.settings,p=state.points||{};return `<section class="panel"><div class="row between"><h2>Channel-point song requests</h2><span id="points-status" class="badge">${esc(p.status||'Disconnected')}</span></div><form id="rewards-form"><div class="fieldgrid">${toggle('Enable channel-point requests','points_enabled',c.points_enabled)}<label>Song-request reward<select name="reward_id" id="reward-picker">${rewardOptions()}</select></label></div><p id="reward-help" class="hint">${esc(rewardHelp(p.reward))}</p><p id="points-error" class="error">${esc(p.error||'')}</p><div class="savebar"><button type="button" id="load-rewards">Refresh Twitch rewards</button><button class="primary">Save reward settings</button></div></form><p class="hint">Sign in as the channel owner and enable “Require Viewer to Enter Text” on the Twitch reward. Viewers enter a Spotify track or YouTube video link. Stop the bot before changing the selected reward; start it after saving.</p></section><details class="panel"><summary>Create a new reward</summary><div class="fieldgrid"><label>Reward name<input id="new-reward-title" value="NextUp SongRequest" maxlength="45"></label><label>Point cost<input id="new-reward-cost" type="number" min="1" max="1000000" value="${c.reward_cost}"></label></div><button type="button" id="create-reward">Create song-request reward</button></details><div class="row"><button data-nav="connections">Twitch integration</button><button data-nav="rules">Request rules</button></div>`;}
async function loadTwitchRewards(){const result=await api('rewards',{});twitchRewards=result.rewards;await refresh(false);const picker=document.querySelector('#reward-picker');if(picker)picker.innerHTML=rewardOptions();const help=document.querySelector('#reward-help');if(help)help.textContent=rewardHelp(twitchRewards.find(r=>r.id===picker.value));}
function syncRewardStatus(){const p=state.points||{},status=document.querySelector('#points-status'),error=document.querySelector('#points-error');if(status)status.textContent=p.status||'Disconnected';if(error)error.textContent=p.error||'';}
document.addEventListener('change',e=>{if(e.target.id==='reward-picker'){const r=twitchRewards.find(r=>r.id===e.target.value);document.querySelector('#reward-help').textContent=rewardHelp(r);}});


for(const p of ['spotify','youtube','twitch'])document.querySelector('.'+p+'-symbol').innerHTML=uiIcon(p);
document.querySelector('#menu-toggle').innerHTML=uiIcon('menu');

function syncNavOverflow(){
  const nav=document.querySelector('#navigation'),button=document.querySelector('#nav-more');
  if(!nav||!button)return;
  const bottom=nav.scrollTop+nav.clientHeight>=nav.scrollHeight-8;
  button.hidden=nav.scrollHeight<=nav.clientHeight+2;
  button.textContent=bottom?'Back to top ↑':'More tools ↓';
  button.title=bottom?'Scroll to the first navigation options':'Scroll to more navigation options';
  button.setAttribute('aria-label',button.title);
}
document.querySelector('#nav-more').addEventListener('click',()=>{
  const n=document.querySelector('#navigation');
  n.scrollTo({top:n.scrollTop+n.clientHeight>=n.scrollHeight-8?0:n.scrollHeight,behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});
});
document.querySelector('#navigation').addEventListener('scroll',syncNavOverflow);
window.addEventListener('resize',syncNavOverflow);
