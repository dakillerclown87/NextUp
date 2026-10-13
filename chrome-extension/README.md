# NextUp browser extension — beta.11

One shared set of JavaScript files, with two browser packages. The extension
controls one selected YouTube tab through the NextUp app on the same Windows PC.
It does not bypass ads, sign-in, region, age or unavailable-video restrictions.

## Which package?

| Browser | Package | Installation |
| --- | --- | --- |
| Chrome 120+ | Chromium ZIP | chrome://extensions → Developer mode → Load unpacked |
| Microsoft Edge | Same Chromium ZIP | edge://extensions → Developer mode → Load unpacked |
| Brave | Same Chromium ZIP | brave://extensions → Developer mode → Load unpacked |
| Opera / Opera GX | Same Chromium ZIP | opera://extensions → Developer mode → Load unpacked |
| Vivaldi | Same Chromium ZIP | vivaldi://extensions → Developer mode → Load unpacked |
| Firefox 140+ | Firefox ZIP (unsigned test build) | about:debugging → This Firefox → Load Temporary Add-on → manifest.json |
| Safari / mobile | Not included | Requires a separate platform port and packaging |

Use a current desktop version of the listed Chromium browsers. Compatibility is
implemented using their shared extension APIs; live testing in every browser is
not available here. Both API families are tested with simulated browser/media
APIs and the real NextUp server. Firefox's manifest passes Mozilla web-ext lint.

**Firefox installation limitation:** temporary add-ons disappear when Firefox
restarts. A permanent release requires Mozilla signing through a publisher's AMO
account. This package is not signed or published. No browser security setting
changes are required for temporary testing. See the publisher instructions below.

## Install and pair

1. Install **NextUp beta.37** or newer for the updated cross-platform handoff.
2. Extract the appropriate ZIP to a permanent folder. Select its manifest.json
   directory with Load unpacked (or manifest.json with Firefox's temporary loader).
3. Open NextUp → Connections → YouTube playback. Choose **Browser extension ·
   YouTube tab**, then **Save connections**. Finish the current song first.
4. Click **Generate browser pairing code** and **Copy pairing code**. Open the
   NextUp extension, paste it and click **Pair with NextUp** within three minutes.
5. Click **Open YouTube tab**, or use **Use this YouTube tab** on an existing tab.
   Complete any YouTube sign-in/consent and click Play once if autoplay is blocked.
6. Enable **Stream widgets → Equalizer audio → Motion → Follow NextUp playback**
   once. The choice persists. No browser-name or PID setting is needed.

Keep NextUp, your browser and the selected YouTube tab running. Only one browser/
profile can be paired at a time. Switching browser requires disconnecting the
old extension and pairing the new one once; ordinary song transitions require no
manual source change. A revoked/disconnected extension pauses managed playback.
For playback safety, reconnecting does not automatically resume a stopped queue.

## Updating an existing unpacked extension

Replace the files in the extension's existing folder with beta.11, click Reload
on the browser's extensions page, then refresh the selected YouTube tab. If the
connection was stopped, reconnect and resume the queue in NextUp. This build
reports the actual media end immediately and holds managed playback against
YouTube autoplay while the next song loads. It does not bypass advertisements.

## Automatic equalizer following

Spotify songs use Spotify's local process. External YouTube songs use the actual
browser process associated with the authenticated extension's localhost socket.
Windows resolves its TCP connection to a process and walks to that browser's
process-tree root. Supported names: chrome.exe, msedge.exe, brave.exe, opera.exe,
vivaldi.exe and firefox.exe. Embedded YouTube uses NextUp's own process tree.

This avoids guessing from browser names or capturing a different open browser.
If the connection cannot be resolved, the equalizer waits and retries; it never
falls back to another browser or all PC audio. Audio may include other tabs in
the same process tree. Windows build 20348+ is required. Process discovery and
WASAPI capture are cross-compiled but still need actual Windows validation.

## Update from NextUp / older NextUp extension

Pause playback, copy the Chromium ZIP's contents into the **same extension
folder**, replacing its files, and click **Reload** on the existing extension.
Refresh the YouTube tab too. Keep the same folder/extension entry to preserve
its ID and pairing. If changing browser or folder, pair again. Firefox is a
separate build with its own ID. Extension ZIPs do not update automatically from
the stores; signed/published releases can add store updates later.

## Privacy

The extension accesses only YouTube and http://127.0.0.1:8888, with local storage
and reconnect alarms. It sends a local player-only pairing credential and the
selected tab's playback state to NextUp on this PC. It does not send that data to
an external extension service or receive Spotify/Twitch credentials. It does not
collect chat messages or browse unrelated tabs. Firefox's required data-use
categories declare the local authentication and playback-state exchange.

Raw music audio is handled by NextUp's optional Windows capture component,
not recorded by the extension. Only spectrum levels reach widgets. Disconnect
and forget pairing removes the extension credential; Forget browser revokes it
in NextUp. No Native Messaging host or additional audio install is required.

## Shared source and publisher builds

Run `python tools/build_extensions.py`. It creates Chromium Manifest V3 and
Firefox Manifest V2 packages in dist/ from the same chrome-extension/ files.
Firefox uses a persistent background script for the local playback connection;
Chromium uses a service worker. The Firefox build uses the promise-based browser
API, and Chromium uses chrome. Storage access-level guards apply where supported.
Permissions and code changes belong in this shared source, not generated ZIPs.

For a permanent Firefox package, test on Firefox, review Mozilla's policies/data
consent declaration and submit this source to AMO for signing (listed or unlisted)
using your publisher account. Retain the ID nextup-player@nextup.local for updates
or choose your own publisher ID before first publication. No signing keys or
publisher credentials are included. Store publishing is not performed here.

## References

- https://learn.microsoft.com/en-us/microsoft-edge/extensions/
- https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Build_a_cross_browser_extension
- https://extensionworkshop.com/documentation/develop/temporary-installation-in-firefox/
- https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/
- https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/
- https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getextendedtcptable

Beta.11 checks the actual media while the page is loading, retries transient play interruptions and replaced video elements, and can refresh the selected tab once if its content script stops responding. It still waits for actual song playback before confirming a handoff.

## Recovering a missing player connection (beta.12)

The extension now attempts to reattach its player connection to the selected YouTube tab. If playback still cannot connect, open the NextUp extension popup and click **Repair player connection**. Allow this extension to read/change data on `https://www.youtube.com/*` in your browser's extension settings, refresh the YouTube tab, and select it again if required. Page sign-in/consent and autoplay interaction must still be completed in YouTube itself.

For an unpacked Chrome/Edge extension update, extract the new ZIP into your existing extension folder, use Reload on the browser's Extensions page, and refresh the selected YouTube tab. Accept the added scripting permission if prompted. If you load from a new folder and the browser assigns a new extension ID, pair it again in NextUp. The Firefox package is unsigned and requires the existing temporary/developer installation workflow or signing for general distribution.
