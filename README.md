# NextUp

### Your stream. Your community. Your music queue.

**NextUp is an open-source Windows desktop music request app and Twitch bot.** Let viewers request Spotify tracks and YouTube videos through chat or channel points, manage what plays next, and show your music on stream with customizable widgets.

NextUp runs in its own desktop window. The Windows EXE installer includes its Python runtime, so streamers do not need to install Python or run command-line setup scripts.

**Current documented release:** `2.0.0-beta.42` · **Platform:** Windows x64 · **License:** MIT

[Support the project on Ko-fi](https://ko-fi.com/nextupplus)

---

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Connect Twitch](#connect-twitch)
- [Connect Spotify](#connect-spotify)
- [Set up YouTube](#set-up-youtube)
- [Channel-point requests](#channel-point-requests)
- [Request rules and role permissions](#request-rules-and-role-permissions)
- [Chat commands](#chat-commands)
- [Playback and queue modes](#playback-and-queue-modes)
- [Stream widgets](#stream-widgets)
- [Moderator access](#moderator-access)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Contributing](#contributing)

## Features

### Music and playback

- Spotify Premium playback controls and playback-device selection.
- YouTube playback through NextUp's player or a paired browser extension.
- A mixed Spotify/YouTube queue that coordinates playback between sources.
- An optional Spotify-native queue mode.
- Drag-and-drop queue ordering, approval, removal, skip, and vote-to-skip controls.
- A Spotify playlist browser for adding tracks to the request queue.
- Spotify or YouTube fallback playlists with saved positions for when viewer requests run out.
- Live song information, album artwork, progress, and a separate player/queue popout.

### Twitch requests and moderation

- Song requests through customizable chat commands or channel-point rewards.
- Select rewards created on Twitch or create a reward through NextUp.
- Separate rules for viewers, subscriber tiers 1–3, VIPs, moderators, and the broadcaster.
- Per-role request methods, cooldowns, active-request limits, session limits, and skip permissions.
- Maximum song duration, artist/track blocklists, and explicit-content controls.
- Optional manual approval and paired moderator review access.
- Custom text commands with permissions, cooldowns, variables, and randomized reply pools that retain their selection state across restarts.

### Appearance and widgets

- Compact desktop layout, collapsible navigation, dark/light themes, color pickers, and hex colors.
- Separate now-playing and upcoming-queue widgets for browser sources.
- A visual widget editor with movable and resizable elements, layers, custom fonts, images, GIF backgrounds, and animation settings.
- JSON widget import/export, saved previews, and **Save as new widget** to preserve original designs.
- Decorative equalizers or optional application-audio analysis that can automatically follow Spotify and the connected YouTube player.
- Local diagnostics and support for verified GitHub updates after publisher configuration.

> This package contains NextUp only. It does not include an audio-recognition app or cloud-account service.

## Requirements

| Component | Requirement |
| --- | --- |
| Desktop app | Updated 64-bit Windows 10 or Windows 11; Windows 11 recommended |
| Desktop interface | Microsoft Edge WebView2 Runtime; setup includes its installer if needed |
| Online services | Internet access and the accounts/API credentials for the integrations you use |
| Twitch | A Twitch account and a Public Twitch application Client ID |
| Spotify playback | Spotify Premium, an authorized Spotify application Client ID, and an available playback device |
| YouTube metadata/search | A Google Cloud API key with YouTube Data API v3 enabled |
| Reactive equalizer | Windows build 20348 or newer, with audio playing on this PC |

Only configure the music services you intend to use. Ordinary EXE users do not need Python, Node.js, or build tools.

The supplied beta does not include shared Spotify/Twitch developer credentials. These must be configured before connecting. A Client ID identifies an application; it does not replace the user's sign-in or grant access by itself.

## Installation

**Clean distribution:** use the published installer or source archive. Do not upload your installed `userdata` folder. Release packaging excludes credentials, local settings, databases, private signing keys, and build caches. Users connect their own accounts after installation. The Ko-fi support link remains part of the app; it does not activate a membership.

1. Open this repository's **Releases** page and download the published Windows installer, such as `NextUp-Setup-2.0.0-beta.42-x64.exe`.
2. Close an existing NextUp instance before installing an update.
3. Run the installer and launch **NextUp** from its shortcut.
4. Open **Settings** and choose **Integrations** from the section dropdown.
5. Connect Twitch and your chosen music source using the steps below.
6. Configure request rules, start the bot, and use **Queue → Start / resume** when ready.

If this repository only contains source code, its maintainer must build and publish an installer first. GitHub's **Download ZIP** button downloads source, not a ready-to-run Windows installer.

NextUp opens in its own window. Provider sign-in opens your browser. Minimizing keeps the app running; closing the main window exits it.

Settings, account connections, widgets and queue data live in `%LOCALAPPDATA%\NextUp\userdata`, separately from installed application versions.

- **Updating NextUp:** close the app and run the newer installer normally. Do not uninstall or delete `userdata`. The installer updates the program and preserves your existing settings and account connections. Reauthorization may be necessary if a provider revokes a login or a future feature needs additional permissions.
- **First installation:** users connect their own accounts. No creator account is included.
- **Legacy SongScout installations:** this standalone NextUp distribution does not import that separate application's saved account files automatically.

For GitHub, upload the generated release installer and the reviewed source archive, never your installed NextUp folder or `userdata`. Public packaging excludes saved accounts, settings, local databases and private signing keys. In-app updates require configuring your repository and signing keys first; distributing a newer EXE works without that setup.

## Connect Twitch

1. Open the [Twitch Developer Console](https://dev.twitch.tv/console/apps).
2. Register an application using Twitch's current registration requirements, including verified email and two-factor authentication. Choose the **Public** client type for NextUp's desktop device-code login.
3. If the registration form requires an OAuth redirect URL, use `https://localhost:3000` as the placeholder shown in NextUp. Desktop Twitch sign-in uses a device code and does not send its callback there.
4. Copy the application's **Client ID**.
5. In **Settings → Integrations**, enter the **Public Twitch Client ID** and **Channel login**. Use the channel's login name, without a URL or `#`.
6. Click **Save connections**, then **Connect Twitch**.
7. Follow the browser prompt and approve the displayed login code if requested.
8. Return to NextUp and click **Start bot**.

For channel points and complete subscriber-tier verification, sign in as the broadcaster who owns the configured channel. Basic chat use in another channel depends on that channel's chat permissions.

See Twitch's [application registration](https://dev.twitch.tv/docs/authentication/register-app) and [device-code authentication](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#device-code-grant-flow) documentation.

## Connect Spotify

1. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create or select a Web API application.
2. Add this exact redirect URI to its settings:

   ```text
   http://127.0.0.1:8888/callback/spotify
   ```

3. Copy the **Client ID** into **Settings → Integrations → Spotify**.
4. Click **Save connections**, then **Connect Spotify**, and authorize your account.
5. Open Spotify on your intended playback device and play a track once so the device becomes available.
6. In NextUp, click **Find playback devices** and select that device.

NextUp uses PKCE authentication; no Spotify Client Secret is entered into the desktop app. The redirect address must match exactly—do not replace `127.0.0.1` with `localhost`.

Spotify Premium is required for playback controls. Development-mode applications also have account, allowlist, and API-access restrictions. If another account cannot connect or use an endpoint, review the application's access settings and Spotify's [current quota-mode requirements](https://developer.spotify.com/documentation/web-api/concepts/quota-modes). Publishing NextUp does not automatically remove Spotify's restrictions.

## Set up YouTube

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or select a project.
2. In **APIs & Services → Library**, enable **YouTube Data API v3**.
3. In **APIs & Services → Credentials**, create an API key. Restrict its API access to YouTube Data API v3.
4. Enter the key in **Settings → Integrations → YouTube** and save.
5. Choose a playback mode:

| Mode | Setup |
| --- | --- |
| NextUp embedded player | Select this mode and click **Open YouTube player**. Keep its window open. |
| Browser extension · YouTube tab | Install the NextUp extension, generate a browser pairing code in NextUp, pair the extension, and select a YouTube tab. |

For Chrome, extract the Chromium extension package to a permanent folder, open `chrome://extensions`, enable **Developer mode**, and choose **Load unpacked**. Select the folder containing `manifest.json`.

The Chromium package also targets Edge, Brave, Opera/GX, and Vivaldi. Firefox has a separate package; unsigned temporary installs disappear when Firefox restarts. Safari and mobile browsers are not included.

See the [extension installation guide](https://github.com/dakillerclown87/NextUP-Chromium-Extension) and [YouTube API setup documentation](https://developers.google.com/youtube/v3/getting-started).

Complete any YouTube consent/sign-in prompt and click Play once if the browser blocks autoplay. The **YouTube Connected** indicator reports player connectivity, not Google account login or API-key validity. Video availability, region, age, and embedding restrictions still apply.

## Channel-point requests

### Use a reward you already created on Twitch

1. Sign into NextUp as the channel owner.
2. On Twitch, edit your reward and enable **Require Viewer to Enter Text**.
3. In NextUp, open **Rewards → Refresh Twitch rewards**.
4. Select the reward, enable channel-point requests, and click **Save reward settings**.
5. Start the bot. Viewers enter a Spotify track link or YouTube video link when redeeming.

### Create a reward through NextUp

Open **Rewards**, expand the creation section, enter the title and cost, and create the reward. The default title is **NextUp SongRequest**; it can be changed.

Rewards are linked by ID. Renaming a selected reward on Twitch preserves its connection. Deleting and recreating it produces a different ID, so select it again. Stop the bot before switching rewards.

> Twitch only lets the application that created a reward retrieve its redemption history or automatically fulfill/refund it. Rewards created directly on Twitch support live requests while NextUp is connected, but require manual fulfillment/refunds in Twitch and cannot recover missed offline redemptions through NextUp. See the [Twitch API reference](https://dev.twitch.tv/docs/api/reference/#get-custom-reward-redemption).

## Request rules and role permissions

Open **Settings → Requests** to configure approval, explicit songs, unknown lyric ratings, maximum length, blocklists, and queue limits. The duration field displays a minutes-and-seconds readout; `360` seconds is `6:00`.

Under **Privileges by role**, choose a request method for each role:

| Method | Behavior |
| --- | --- |
| Either method | Accept chat commands and channel-point requests |
| Channel points only | Require the configured channel-point reward |
| Chat command only | Accept the request command; reject point redemptions |
| Requests disabled | Reject viewer requests for that role |

To require points for regular viewers while allowing subscribers, VIPs, and moderators to use `!sr`, click **Viewers use points; other roles use either method**, then **Save request rules**. Enable and select the reward in **Rewards** too.

The highest verified role applies: **broadcaster → moderator → tier 3 → tier 2 → VIP → tier 1 → viewer**. Active limits include queued and playing requests. A session limit of `0` means unlimited. Desktop-owner additions bypass viewer request-method restrictions.

YouTube metadata cannot reliably identify explicit lyrics or verified artist credits. Unknown-rating review is available, but automatic filtering cannot guarantee clean lyrics.

## Chat commands

These are the defaults; rename them on the **Commands** page.

| Command | Action |
| --- | --- |
| `!sr <song link>` | Request a Spotify track or YouTube video |
| `!queue` | Show upcoming requests |
| `!remove` | Remove your most recent pending request |
| `!remove <request ID>` | Remove a specific request you own, if removable |
| `!np` | Show the current song |
| `!skip` | Skip when direct skipping and your role's permission allow it |
| `!voteskip` | Vote to skip when vote-to-skip is enabled |

**Chat and channel-point requests require a track/video link.** Use the launcher to search by song name. Requests confirm the title, artist or channel, and platform.

Custom commands support text replies and variables such as `{user}`, `{channel}`, `{args}`, `{song}`, `{artist}`, `{platform}`, and `{queue_count}`. They do not execute arbitrary scripts. No built-in recognition or fun-command engine is included.

## Playback and queue modes

### Mixed Spotify and YouTube

Choose **Both sources** on Home. NextUp manages the order and coordinates source changes with **Use Spotify’s queue** either enabled or disabled. Reorder upcoming unsent songs by dragging them or using the queue controls.

### Spotify-native queue

Enable **Use Spotify’s queue** to stage the next eligible Spotify request in Spotify. NextUp still controls the overall order: Spotify → Spotify → YouTube → Spotify works in that order. A Spotify request is not staged past an intervening YouTube request. Spotify does not hold YouTube videos; NextUp pauses and switches players at the boundary.

Spotify's API cannot remove or reorder submitted entries. Sent entries must be edited in Spotify, then forgotten in NextUp if needed. If Spotify's queue differs from the expected request, NextUp starts the requested track directly instead of following unrelated songs. Keep NextUp running to coordinate the sequence.

### Fallback playlist

Open **Queue → Fallback playlist**. Choose your preferred fallback platform, enter its playlist link, enable fallback music, choose shuffle/repeat, and save. Use **Both sources** for mixed playback. Spotify requires Premium; YouTube requires the existing API key and an active embedded or paired browser player. YouTube playlists must be accessible with the API key.

When requests run out, NextUp starts the selected playlist even if Spotify would otherwise continue unrelated music. New requests follow the current fallback track. After requests finish, the playlist continues with its next unplayed song. Spotify and YouTube maintain separate saved positions per playlist, including across app restarts. This saves playlist position, not the exact second within a song. Turn Shuffle off to follow playlist order. Fallback does not generate recommendations.

Up to 500 entries are loaded; unavailable videos and songs blocked by artist, duration or known-explicit rules are skipped. Selecting a fallback playlist approves its unrated videos. Saving enabled fallback starts it when the managed queue is empty, including replacing unrelated Spotify playback; an explicit Pause remains paused.

### Restart behavior

Queued requests are stored locally between launches. A previously playing managed request returns to the pending queue. NextUp does not automatically resume managed playback on launch; review the queue and use **Start / resume**. Spotify-native playback and tracks already submitted to Spotify remain subject to Spotify's own state.

## Stream widgets

1. Open **Stream widgets**.
2. Choose a preset, customize a copy, or import a NextUp JSON widget.
3. Edit its layout, colors, fonts, artwork, background, and animations.
4. Click **Save as new widget** to preserve the original, or **Save changes** to update a saved design.
5. Open its saved preview, then copy the widget URL.
6. Add a **Browser Source** in OBS Studio or Streamlabs, paste the URL, and use the canvas dimensions shown in the editor.

Keep NextUp running. Widgets display the music state reported by NextUp; they do not identify music from arbitrary browser tabs. Browser-source widgets show metadata and graphics, not audio.

Drag elements to move them and use resize handles to adjust their size. JSON exports include supported image/font assets. GIF backgrounds are supported, with practical file and rendering limits documented in the [advanced widget guide](docs/WIDGET-DESIGNER-V3.md).

For music-reactive equalizers, choose **Equalizer audio → Motion → Follow NextUp playback**. This follows local Spotify audio and the selected YouTube player automatically. Browser capture can include other tabs in the same browser process. Remote Spotify Connect audio is not captured on this PC.

StreamElements requires an HTTPS widget URL. NextUp's optional tunnel needs `cloudflared` installed and exposes the read-only widget service on port `8889`. Temporary URLs change after restarting the tunnel. Keep the admin service on port `8888` private.

## Moderator access

Open **Queue → Moderators & request approval**, enable moderator access, enter a label, choose approve/reject permissions, and generate a pairing code.

Share the review link and code privately. Codes are single-use and expire after 10 minutes. You can revoke access in NextUp. Remote review requires the optional internet link and `cloudflared`.

**The label is not Twitch identity verification.** Access belongs to whoever successfully pairs with the code. It does not automatically confirm that person's Twitch username or moderator status.

## Troubleshooting

| Problem | Check |
| --- | --- |
| Connect does not complete | Save the Client ID first. Confirm the provider's app settings and finish browser authorization. |
| Spotify does not play | Confirm Premium, open Spotify, play a track manually, then refresh/select its device in NextUp. Check track availability and Diagnostics. |
| YouTube does not play | Keep the selected player/tab open, check extension pairing, and complete consent or autoplay prompts. |
| A request needs approval | Review request settings and unknown lyric ratings, then approve it in Queue. |
| Channel points do nothing | Confirm broadcaster sign-in, selected reward ID, required text input, enabled points, and a running bot. |
| Viewer cannot use `!sr` | Check that viewer's effective role and its request method. Points-only roles must redeem the reward. |
| Widget is empty or stale | Keep NextUp running, save the design, and refresh the browser source using its current URL. |
| A collapsed panel is missing | Use **Expand all** in the top toolbar. |
| In-app updates are unavailable | Signed updates need publisher configuration; see the publishing guide below. |

Use **Settings → Diagnostics** to inspect errors. Include the app version, reproduction steps, and a redacted diagnostic export in a GitHub issue. Do not publish tokens, API keys, pairing codes, or widget access keys.

## Development

Use standard **64-bit Python 3.13** for source development. End users installing the EXE do not need it.

From the extracted or cloned repository root on Windows:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m studio.desktop
```

Run the Python tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_studio
```

| Folder | Purpose |
| --- | --- |
| `studio/` | NextUp desktop app, providers, queue, and widgets |
| `chrome-extension/` | Shared browser-extension source |
| `docs/` | Build, publishing, audio, and widget guides |

- [Build Windows installers](docs/WINDOWS-BUILD.md)
- [Configure signed GitHub updates](docs/PUBLISHING.md)
- [Build browser extensions](chrome-extension/README.md)

In-app updates require a configured repository, signing key, and published release assets. Normal versioned app/runtime updates can use this system; changes to the stable native launcher/bootstrap may still require a new installer. Installer Authenticode signing is separate from update signing; supplied beta installers are unsigned.

## Contributing

Bug reports, documentation improvements, and pull requests are welcome. Explain the problem, describe the change, and include relevant validation. Test live playback and native Windows behavior when changing those integrations.

Keep credentials, local user data, private signing keys, and generated runtime files out of commits. Share only widget assets and fonts you have permission to redistribute.

## Support the project

If NextUp helps your stream, you can support its development on Ko-fi:

**[Support the project → ko-fi.com/nextupplus](https://ko-fi.com/nextupplus)**

## License

Project code is available under the [MIT License](LICENSE). Third-party dependencies, fonts, artwork, and platform services retain their own licenses and terms.

### Mixed Spotify / YouTube handoffs

For beta.42, update the browser extension to beta.10 as well: replace its unpacked
files, reload the extension and refresh the selected YouTube tab. NextUp holds
YouTube locally at a song's end and pauses Spotify at a verified boundary before
switching. Spotify's small boundary guard may trim up to 0.4 seconds; provider
loading, ads and network latency can still introduce a gap. Spotify crossfade or
Automix can start another track earlier, so disable these for predictable mixed
queues. Spotify queue integration uses the same managed boundary handling.

### Adding a song from the launcher

Paste a Spotify track or YouTube video link and click **Add song**. NextUp detects
the service from the link; the provider dropdown applies only to artist/title
searches. Search by name, then choose a result to add it. Successful additions
clear the input and result cards. If a request fails, its error appears beside the
form and the input remains for correction. Adding through the launcher counts as owner approval: unrated YouTube videos
do not need another approval in Queue. Viewer requests retain their review rules.
Artist, track, length and known-explicit blocks still apply.

Fallback troubleshooting: after saving, click **Check saved playlist** in Queue. This checks access and request rules without starting playback or changing the playlist position. Spotify's playlist-items endpoint requires ownership or collaborator access; following someone else's playlist is insufficient. If access fails, use a playlist you own or collaborate on, or reconnect the correct Spotify account. NextUp displays the HTTP error in the fallback panel. Saving enabled fallback retries an idle failed start; an explicit Pause remains paused.

### Widget studio

Open **Stream widgets** to choose a saved design or import a widget JSON file. The compact editor provides a live canvas, two to eight progress colors (picker or hex), and smooth border lighting with adjustable colors and speed. Expand **Layout, layers & advanced settings** for geometry, artwork, fonts, images and animation. Add a shape layer to enable border lighting on a new design.

Choose **Save as new widget** to preserve the original. **Export this design** creates a portable JSON file; **Copy this widget URL** supplies the browser-source URL for OBS. The editor's controls are not part of the streamed widget. **Preview song transition** runs a demonstration without changing playback. Halo and Automata examples are in `docs/Halo-Orbit-Glow.json` and `docs/Automata-Gradient.json`; these effects require beta.42 or later. JSON widgets contain data, not executable scripts.

In beta.42 the visible **Layers** list selects covered layers. Use **Send to back** or **Bring to front**, or drag the selected layer with the small move handle above its selection box. New shapes start behind existing content. **Play layer motion** previews pulse/float/spin in the editor; choosing a motion starts its preview automatically. Stop it for precise positioning. Border lights follow layer motion, including pulse. System reduced-motion settings are respected and explained in the editor.
