# beta.42 widget layer and motion validation

- 251 Python regression tests passed.
- Real launcher/API UI test: select a title fully covered by a foreground shape, move it using its raised handle, send the covering shape to back, and click the title again.
- Renderer assertions: pulse scale and opacity change; the outer layer no longer clips growth; border canvas uses the same animated transform; stopping cancels preview motion; playback pause holds the demo; reduced-motion mode is explained and does not animate.
- Saving retains motion settings. Source and Windows payload undergo the distribution audit.
- Installer reuses unchanged native launch/audio binaries and pinned runtime from the official beta.41 installer. The repack tool rejects changed native source or icon. No local accounts or user data are included.
- Windows/WebView2 execution cannot be tested in this Linux environment.

# beta.41 widget studio validation

- 251 Python regression tests passed, including native effects save/export/reload and invalid-input validation.
- Real local launcher/API UI checks passed in headless Chromium: JSON import, 6/8 palette selection, live hex edits, save/export/reload, border toggle, song transition preview and a 760px viewport without horizontal overflow.
- Widget studio screenshot inspected and layout corrected after the first render.
- Windows installer is cross-built. Native WebView2 and real OBS playback cannot be exercised in this Linux build environment.

# NextUp validation

Run `python -m unittest discover -s tests_studio -v` for policy, provider,
queue, playback, packaging, updater, widget and local-service regressions.
Run `node tools/test_redesign_ui.cjs` with the Playwright test dependencies and
NEXTUP_TEST_CHROMIUM set to an available Chromium binary for UI checks.
Build the Windows installer with `python tools/build_windows.py --product nextup`.

Linux cross-compilation is not a Windows execution test. Before public promotion,
validate installer startup, Twitch/Spotify sign-in, source switching, browser pairing,
local audio capture and OBS widgets on a clean Windows account.

## beta.37 handoff regression checks

- 229 Python tests passed, including verified Spotify boundary handoff, pause
  failure retention, adaptive polling and pause-before-fallback lookup.
- 11 JavaScript tests passed, including immediate YouTube end reporting, local
  autoplay blocking, ad exclusion and embedded-player hold/release.
- Run `NODE_PATH=<dependencies> node tools/test_chrome_transport.cjs` for real
  extension scripts + the local service with simulated browser/media/Spotify.
  Set `NEXTUP_TEST_BROWSER=firefox` to exercise the Firefox API adapter.
- These checks do not establish live Spotify/YouTube timing on a user's Windows
  device. Final handoff latency depends on provider and network response times.

## beta.38 request form and upgrade checks

- 234 Python tests passed. Direct links route by URL, name searches use the
  selected provider without queueing, invalid links return visible errors, and
  existing block/review rules continue to apply.
- `tools/test_song_input_ui.cjs` passed against the real launcher page and local
  API in headless Chromium, with provider metadata simulated. It covers a Spotify
  request followed by YouTube, provider/link mismatch, stale result clearing,
  one-click result selection, visible failures and duplicate-submit protection.
- Installer activation was exercised with a simulated runtime preflight: account,
  configuration and queue fixture bytes survived unchanged. Existing signed-update
  preservation and fresh-install privacy tests also passed.
- Windows execution and live third-party account calls were not available here.

## beta.39 owner approval, mixed Spotify queue and fallback checks

- 243 Python tests passed, including the actual conductor + Spotify adapter with
  simulated service responses for Spotify → Spotify → YouTube → Spotify, then
  either fallback platform, request priority and resumption at the next playlist
  song. Separate tests cover persisted YouTube positions, independent provider
  cursors, playlist pagination, failed starts, uncertain appends, blocked tracks,
  selected-device resume, and preservation of viewer review rules.
- The real launcher UI + local API test passed with unrated YouTube metadata and
  review enabled: Home additions appear immediately without a second approval.
  It also checks mixed-source Spotify queue settings and YouTube fallback fields.
- No live Spotify/YouTube account or Windows installation was available. Provider
  delays, autoplay/crossfade, externally edited Spotify queues and browser ads
  still need live Windows testing. The browser extension remains beta.10.

## beta.40 fallback recovery

- 249 Python tests passed, including a failed playlist load after a YouTube song ends, retry into the selected playlist, playlist access error propagation, bounded scans, and check-without-playback/cursor changes.
- Actual launcher UI exercised in headless Chromium: saved YouTube fallback settings and the new check button show the provider error and re-enable the button. Existing request-form checks passed.
- Spotify API calls in these tests use simulated responses. No live Spotify account or Windows desktop execution was available.
