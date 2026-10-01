# Privacy

NextUp runs on your computer. This standalone build has no cloud account,
membership, configuration-backup, usage-telemetry, advertising or recognition service.
Network connections support Spotify, YouTube, Twitch and user-requested GitHub updates.
The Ko-fi support button opens the project's public support page in your browser.

Local data includes settings, OAuth tokens, API keys, queue entries, requester IDs,
redemption IDs, playback history and diagnostics. Windows account tokens use DPAPI;
protect your Windows account and local backups. Settings are stored under
`%LOCALAPPDATA%\NextUp\userdata`. Uninstall preserves this folder; remove it separately
if you want to erase your personal data. No old installation is automatically imported.

Widgets display playback metadata. Anyone given a widget URL/access key can see
its output. Optional cloudflared links expose only the widget or moderator service,
not the admin service. Moderator labels do not verify Twitch identity; share codes
privately and revoke access when no longer needed.

Optional application-audio analysis computes spectrum levels locally. It does not
submit recordings to a recognition provider. Browser capture can include other tabs
in the same process tree. No general chat transcript archive is maintained.

Release builds exclude local data, accounts, keys and logs. Do not publish a copy of
your installed application folder or private configuration backups.
