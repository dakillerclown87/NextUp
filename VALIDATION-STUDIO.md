## beta.64 update retention and publishing checks

380 Python tests and 28 JavaScript tests passed. Sixteen new regression cases
cover install/staged-update activation, repeated upgrades, same-version repair,
rollback, failed preflight, locked old files and retry, invalid/missing markers,
protected pending versions, unrelated folders/directory links, unchanged saved
data, invalid publisher configuration, preservation of an existing trust anchor
and signing-key/repository validation before release builds.

Installer payload extraction, source equality, PE integrity, pinned dependency
checks and distribution audits are performed before delivery. Native Windows
installation is not executable in this Linux environment. The GitHub publisher
remains unconfigured; tests use fixture keys and do not publish a release or
prove a live update feed. No Spotify playback logic changed.

## beta.59 repeated skips release gate

337 Python tests and 27 JavaScript tests passed. The targeted suite contains 11 cases and passed with NEXTUP_SKIP_SOAK=1000, routing every skip through the actual /api/playback handler and actual Spotify adapter with simulated HTTP responses. This ran before the beta version was incremented or installer build began. Full details, failure conditions and limitations are in docs/PLAYBACK-REGRESSION-beta59.md.

The beta.58 code failed the new second-skip/context-reload and already-playing-position tests. A further test caught the launcher route treating a Skip during pending fallback recovery as Start; this was fixed and retested. Coverage includes delayed status after the second skip, no additional writes after acknowledgment, preserved position, playlist identity, rapid overlapping clicks, YouTube/viewer priority, pause cancellation, explicit skip during recovery and wrong context/device rejection.

Windows package archive/checksum, source equality and distribution privacy audits are checked during packaging. No live Spotify account or Windows execution was available; passing a simulator does not prove the service cannot misreport playback.

## beta.58 stale banners and delayed display

326 Python tests and 27 JavaScript tests passed; app.js syntax checked. New tests exercise success during retry backoff, passive recovery before its deadline, no extra control writes during status-only checks, saved fallback late success, incoming metadata visible while the provider start call is blocked, scoped banner clearing, a late failed response followed by a fresh successful state, preservation of unrelated errors, and pending track rendering with Starting status. The full suite includes the default playlist/adapter simulations; the extended 12,000-transition run documented under beta.57 was not repeated for this UI/recovery-timing change.

Installer archive integrity, SHA-256 and distribution audits checked during packaging. Native Windows execution and live Spotify playback are unavailable here. JavaScript tests execute the production UI functions with simulated DOM/state; no full browser rendering validation is claimed for this release.

## beta.57 Spotify confirmation recovery

321 Python tests and 22 JavaScript tests passed. New fault-injection cases exercise retained viewer requests, native playlist return, resume without duplicate history, delayed confirmation, bounded writes under persistent mismatch, session-deferred fallback tracks, complete fallback failure, device changes, pause during an outstanding status read, and already-consumed native queue entries (including handoff-paused and duplicate-next entries). Extended playlist tests cover 10,000 seeded transitions and 2,000 actual-adapter transitions using simulated Spotify responses.

Windows installer archive/checksum and distribution privacy audits passed. No live Spotify account playback or native Windows installation was available. These tests verify control/recovery behavior with simulated provider responses; they cannot guarantee provider availability or prove that a specific live client no longer stalls.

## beta.56 playlist reconciliation, request capacity and stable overlays

310 Python tests and 22 JavaScript tests passed. Extended run: 10,000 seeded fault-injection transitions plus 2,000 transitions through the actual Spotify adapter with simulated Connect responses, all passed. Cases include crossfades, skipped tracks, long poll gaps, stale/empty responses, request interruptions, delayed confirmation, bounded recovery, explicit pause, 500 background songs with real viewer admission, playlist pagination to 1,201 songs and stable widget keys across app restarts/tunnel activation. Default full-suite runs use shorter soak lengths; README contains the extended command.

JavaScript fixtures verify hidden/shown playlist rows, original reorder indices, separate counts, fallback controls above the list, and overlay offline recovery at the same URL. A full browser preview was attempted but the runtime's Chromium download was invalid, so no visual/browser-engine validation is claimed. Windows installer integrity, runtime checksum, dependency and privacy audits are required by the packaging script. No native Windows installation or live Spotify account playback was performed. Persistent provider/authorization/device failures can still require attention.

## beta.55 active Spotify playlists and saved fallback queue

297 Python tests and 18 JavaScript tests passed. Real conductor and Spotify adapter code were exercised with simulated Spotify Connect responses: 20 natural active-playlist transitions after a request with no pause/start writes, multiple queued requests, approval gates, explicit pause, YouTube/Spotify order, original playlist restoration and preserved shuffle/repeat. A 25-track saved fallback ran across its repeat boundary with requests prioritized and no viewer quota charges for fallback. Tests reject a correct song reported in the wrong playlist context. App JavaScript syntax checked.

The Windows installer reuses unchanged verified native launcher/capture binaries, refreshes the embedded runtime from the pinned official Python archive and audits bundled source/dependencies. Native Windows installation and live Spotify account playback are not available in this environment. Network and cross-platform handoffs are not guaranteed gapless.

## beta.51 artwork colors, moderator desk, browser handoff

263 Python tests passed. Real local-server browser tests verified moderator pairing, now-playing/queue/loaded playlist, incoming requests, approval, restricted-storage sessions and revocation. Equalizer browser tests verified artwork palettes across bar and canvas styles, stale-song responses, custom fallback, caching, editor controls and saved settings. Browser-extension unit fixtures passed for loading-tab confirmation, single reload recovery, transient play failures, ads, end events and pause safety. Installer archive integrity checked. No live third-party YouTube playback or native Windows installation was performed here.

## beta.50 per-widget audio response

261 Python tests passed including input validation and save/export/import persistence. Browser checks verified independent sensitivity, faster attack and fall, bass-only emphasis, bounded peaks, all canvas styles, live sliders, Punchy preset and save persistence. Windows installer archive integrity checked. Native Windows installation/capture not executed here.

## beta.49 LED equalizer

Browser rendering tests confirmed identical cell sizes and unchanged grid coordinates across audio levels, illumination response, stale audio decay, resize, reduced motion, and returning from LED to regular bars. Preview visually inspected. Installer archive integrity checked; official runtime replacement and binary checks from beta.48 remain enabled. Native Windows installation not executed here.

## beta.48 runtime repair

259 tests passed. Found truncated python313.dll and libcrypto-3.dll in the reused beta.41 payload. Refreshed both runtime copies from the checksum-pinned official archive. Extracted the rebuilt installer and compared every unmodified runtime file byte-for-byte with the official archive; all matched. All bundled PE sections are within file bounds and pinned dependencies are present. Windows installation itself was not executed in this Linux environment.

## beta.47 installer repair

257 tests passed, including dependency drift detection and failed activation preserving settings and the current version. Confirmed beta.46 omitted Pillow from its runtime. Beta.47 includes the hash-pinned CPython 3.13 Windows x64 Pillow wheel and native decoder; repacks now reconcile their dependency lock. Windows installer payload integrity and dependency inclusion checked. Native Windows installation was not executed in this Linux environment.

## beta.46 circular equalizers

255 Python tests passed. Browser integration verified all five circular styles react to injected audio levels; selection, fit-to-artwork, saved settings and browser-source rendering passed. Visual preview reviewed for fine dotted bars and the particle sphere. Windows installer archive integrity checked; native Windows capture and installation were not executed in this Linux environment.

# beta.45 artwork and circular equalizer validation

- 255 Python tests passed, including palette extraction, known-provider URL restrictions, monochrome artwork and JSON setting persistence.
- Local app/browser-source UI test verified color application, manual palette fallback selection, circular bars/wave/orb response to injected audio levels, automatic placement and saving.
- Demo video uses procedural artwork and simulated audio levels; it is not a recording of Spotify or Windows capture.
- Native Windows capture, WebView2 and live provider-account playback cannot be exercised in this Linux environment.

# beta.44 light-trail validation

- Browser test verifies a curved historical path during spin (29 px deviation from a straight chord), finite float/pulse/static paths and a stable reduced-motion frame.
- Layer editor regression passed: selection behind shapes, drag handle, order, motion preview, pause, save and reduced-motion behavior. Border opacity follows pulse while its tail retains past positions.
- Preview video uses the original Miffy background with a representative spinning outline. It is a demonstration, not an export of the user's unseen edited lighting settings.
- Installer integrity and packaged-source comparisons are checked. Native Windows/WebView2 execution is unavailable in this environment.

# beta.43 background effects validation

- Original uploaded Miffy v2 JSON tested in the real local app UI: preview leaves draft unchanged; motion upgrade preserves four clouds and eighteen stars; computed cloud transform and star opacity change over time.
- Saving, exporting, reloading and saved browser-source preview retain both effects and the exact embedded background image.
- Backend regression covers v3 effect flag persistence and invalid toggle types. 252 Python tests passed.
- Native Windows execution is not available in this Linux environment; installer uses the unchanged native/runtime components from the previous official installer.

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
