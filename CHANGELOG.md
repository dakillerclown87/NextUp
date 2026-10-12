## 2.0.0-beta.64

- Remove obsolete installed version folders after a successful component check, keeping the active version, one rollback version and any pending update. Saved settings, account connections, queue data and widgets remain untouched.
- Retry locked old files on a later launch; skip cleanup when activation fails or installation markers cannot be verified. Ignore unrelated folders and directory links.
- Validate the GitHub repository, signing keys and version tag before release builds. Prevent accidental replacement of an existing publisher public key during setup.
- Explain incomplete publisher setup in Updates and disable unavailable update checks. A repository and publisher-controlled signing key are still required; this development package does not claim to enable a live GitHub release feed.
- Cleanup requires this installer once because it updates the stable bootstrap. Future signed application updates then use the cleanup automatically.

## 2.0.0-beta.63

- Fix the whole-page jump captured in the beta.62 recording: the brief "Playback updated" notice appeared after a successful command and disappeared on the next state refresh, moving both columns down and back up.
- Remove the routine playback-success banner. Keep other notifications visible above the page without inserting/removing layout height.
- Reproduce the old behavior in Chromium with a delayed follow-up state response: the queue moved 63 pixels. The same real-click test passes after the fix, including notification/error appearance and removal. All 28 JavaScript tests pass.
- This addresses the captured layout shift; native Windows display behavior still needs live confirmation. Spotify playback/playlist logic is unchanged.

## 2.0.0-beta.62

- Fix the remaining control flash immediately after clicking Skip, Play or Pause: apply busy styling synchronously with disabling the controls, before the next status poll.
- Keep existing button tooltips instead of repeatedly inserting and removing a temporary waiting tooltip.
- Reproduced the beta.61 failure in Chromium using the real click handler with a held playback response: controls fell to 40% opacity. The same test now passes across three clicks and 12 animation frames per click, alongside the existing artwork/transition checks and 27 JavaScript tests.
- Spotify playback, playlist and queue logic are unchanged. Native Windows execution remains a separate live validation step.

## 2.0.0-beta.61

- Update the Home/popout Now Playing card in place instead of rebuilding artwork, controls and progress on every playback status change.
- Load and decode incoming artwork before swapping it into a reserved square. Ignore stale image responses after another song or navigation; show a stable placeholder if artwork fails.
- Preserve the last confirmed play/pause icon during a pending transition. Keep controls visually steady while still disabling duplicate commands.
- Verify 30 transition-state updates, delayed and out-of-order artwork, failed images, navigation and compact layouts in Chromium. Spotify playback and queue logic are unchanged from beta.60.

## 2.0.0-beta.60

- Fix playback confirmation for Spotify catalog relinking: verify original and playable track identities using Spotify metadata, retaining playlist position and avoiding a restart of the same recording.
- Resolve equivalent recordings only with verified relink information or matching ISRC, artist IDs, explicit flag and duration; never accept an unrelated track based on its name.
- Bound unresolved same-device confirmation recovery instead of waiting indefinitely. Retain the request and surface the actual observed song without repeated playback commands.
- Add Follow Spotify's current playlist in Queue → Playlist playback. Follow the playlist already playing without importing tracks or saving its link, prioritize viewer requests, and return to the playlist afterward.
- Clear recovered playback warnings and preserve the confirmed play position. Include identity-resolution details in diagnostics.
- Validation: 364 Python tests and 27 JavaScript tests passed. The user confirmed live repeated skips (six or more), natural endings, and return to the Spotify playlist after a request. See docs/PLAYBACK-REGRESSION-beta60.md for scope and limitations.

## 2.0.0-beta.59

- Reproduce a second-skip wrong-track failure and repeated-start position reset using the real conductor/provider code with simulated Connect responses, before changing playback code.
- Use a verified native next-track command for manual saved-playlist skips instead of reloading playlist context on each skip.
- Preserve already-playing target progress and restore lost context at the current position.
- Do not resend an acknowledged playlist start/skip when its confirmation is delayed. Observe for late success, retaining the queue and playlist.
- Fix launcher Skip being treated as Start while an unconfirmed fallback song is retained. Explicit Skip abandons that background song; Pause now targets audio during pending confirmation.
- Record track identifiers/context match and mark late confirmations resolved in Diagnostics.
- Release gate: 337 Python tests, 27 JavaScript tests, and 1,000 successive simulated skips through the launcher API passed before the installer build. No live Spotify/Windows runtime validation is claimed.

## 2.0.0-beta.58

- Read Spotify status during retry backoff instead of waiting before checking for late success. Keep the existing delay and retry budget for playback commands only.
- Scope the launcher notice to its originating operation, replace stale playback failures with current recovery status, and clear them after confirmed playback. Do not clear unrelated errors.
- Prevent a late failed Play response from restoring a wrong-track banner after recovery.
- Display incoming title/artwork during a pending start, with an accurate Starting/Switching status. Refresh local UI state once per second without caching; keep widgets tied to confirmed playback.
- Explain recovery history in Diagnostics without telling users to reconnect for a recovered track mismatch.
- Validate with 326 Python and 27 JavaScript tests, including before-deadline recovery and pending-start display cases. Live Spotify and native Windows execution remain unverified.

## 2.0.0-beta.57

- Extend bounded Spotify confirmation recovery to viewer requests, native playlist returns and resume, in addition to saved fallback playback.
- Keep recoverable mismatches connected and retain requests after retries; switch to read-only monitoring for late confirmation instead of disabling the conductor.
- Defer repeatedly failing background tracks for the session with a five-minute skip budget. Never silently skip viewer requests. Refreshing the playlist retries deferred tracks.
- Check whether Spotify already consumed a native queue entry before sending play/next. Resume a consumed-but-paused entry without skipping a duplicate.
- Avoid duplicate history when recovery confirms the current song. Preserve explicit pauses and device boundaries.
- Report temporary status outages without an unnecessary reconnect instruction.
- Add regression cases for all recovery modes, persistent mismatches, all-background failures, device changes, pause races and native queue consumption.

## 2.0.0-beta.56

- Reconcile saved playlists across crossfades, skipped tracks, stale/empty Connect responses and missed poll boundaries. Confirm unexpected changes twice and adopt allowed same-playlist songs without restarting their audio.
- Preserve the playlist and viewer queue during transient start-confirmation drift, with at most three automatic retries and cancellation on pause. Permanent/device/authorization failures still surface.
- Remove automatic ten-minute playlist reloads from the playback lock. Explicit Check saved playlist refreshes metadata; normal playback reuses the cached list.
- Replace quadratic cursor copies on every background row with one committed playlist cursor. Unchanged queue polls no longer rewrite the database.
- Spotify playlist loading now supports up to 10,000 entries instead of 500. Request capacity counts active viewer requests only, with 0 meaning unlimited. Blocked rows do not occupy active request capacity.
- Add persistent Hide playlist songs, on by default. Move fallback controls above the queue and display separate request/playlist counts.
- Keep local OBS URLs stable when opening temporary HTTPS access, preserve the overlay key across updates/restarts and recover from timed-out widget state requests.
- Extended tests cover 12,000 accelerated transitions and real viewer admission after 500 background songs. No live Spotify account or native Windows installation was available for validation.

## 2.0.0-beta.55

- Follow the playlist already playing in Spotify when an approved request arrives, without importing or saving its link. Saved fallback remains optional and takes precedence when enabled.
- Spotify requests use the native queue in this mode, allowing Spotify-to-Spotify transitions without NextUp pause/start commands. Preserve Spotify's playlist context, shuffle and repeat settings; retain a return point across YouTube/direct-start handoffs.
- Materialize the remaining saved fallback tracks behind viewer requests in NextUp. Replenish after successful starts, retain the confirmed cursor, keep background tracks out of viewer quotas, and preserve playlist order when reordering requests.
- Start saved Spotify fallback with playlist context plus track offset, and verify both track and context. Never substitute an album for the selected playlist.
- Cover 20 natural active-playlist transitions, 25+ saved fallback transitions, multiple requests, approval, pauses, mixed YouTube/Spotify order and wrong-context rejection with simulated provider responses.
- No credentials or saved user data are included. Existing settings remain in the separate user-data folder.

## 2.0.0-beta.54

- Fixed fallback playback losing control when Spotify moves to another song between polls and NextUp misses the final three seconds of the previous track.
- A recent confirmed playing position plus a new playing track on the same device can now establish that the old song finished. NextUp pauses the outside song and follows viewer requests or the saved fallback playlist cursor.
- Manual pauses, changes before the expected song end, device changes and long observation gaps do not trigger the new recovery. The UI progress timer alone cannot advance playback.
- Verified repeated fallback cycles, request interruptions and resume, repeat-off exhaustion, and playlist refresh failures. Playlist errors pause the outgoing source and surface the error instead of adopting outside music.

## 2.0.0-beta.53

- Enforced YouTube Music category for every request and playlist entry, with no disable switch or role bypass.
- YouTube searches request Music results and independently validate resolved video metadata.
- Queue admission, moderator approval, fallback selection and restored queues enforce the rule. Older saved YouTube entries without a verified category remain visible as blocked and can be re-requested for checking.
- Spotify playback and the existing explicit-content, artist and duration restrictions are unchanged.

## 2.0.0-beta.52

- Explicit Spotify Play/Resume now permits one verified album-offset recovery when a different song remains selected on the same device. Late success is checked before retrying; automatic playback retains its external-song protection.
- Resuming a retained Spotify request updates its progress from the confirmed state and clears stale end-of-song detection.
- Extension beta.12 can reattach its packaged player script to the selected YouTube tab after a missing response, and adds Repair player connection. Readiness is reported only after a real content-script response; site-access restrictions remain enforced.
- Added GitHub badge setup instructions and working MIT/Ko-fi README badges. Global user/request telemetry is not enabled.

## 2.0.0-beta.51

- Browser extension beta.11 now checks media during page loading, retries interrupted playback and recovers an unresponsive selected tab once per command. Launcher timeout messages explain the reported wait reason.

- Moderator desk now shows now-playing, all upcoming requests and the loaded fallback playlist. Pairing tolerates unavailable browser storage; polling has timeouts, visible connection status and manual refresh.

- Added per-widget album-artwork colors for every equalizer style, with a smooth palette transition on song changes.
- Custom/theme colors remain available and act as the fallback when artwork is missing. Settings persist in saved/exported JSON.
- Equalizers and progress bars share cached artwork palette requests.

## 2.0.0-beta.50

- Added per-widget sensitivity, attack time, fall time, and bass emphasis controls with live preview, Punchy preset, and reset.
- Settings persist in saved/imported/exported JSON widgets and apply independently to captured audio across all equalizer styles. Existing widgets retain their previous response by default.

## 2.0.0-beta.49

- Replaced stretched LED masks with a stationary grid of equally sized light segments. Audio now changes segment brightness from the bottom up, with stable gaps and no bouncing blocks.
- LED colors still follow widget accents, including saved widgets and OBS sources.
- Switching directly from a canvas equalizer back to ordinary bars restores the bars.

## 2.0.0-beta.48

- Replaced two truncated runtime DLLs with files from the checksum-verified official embedded Python archive.
- Runtime files are now refreshed from that archive on every repack; Windows binary section bounds are checked before packaging.
- Installer distinguishes an actual application lock from runtime startup failure and records startup results even when Python cannot start.

## 2.0.0-beta.47

- Fixed installer activation failure caused by missing Pillow in the Windows bundle.
- Repacked releases now reconcile pinned runtime dependencies instead of blindly reusing an older runtime.
- Preflight checks the image decoder and saves failure details to install-diagnostics.txt. Activation errors no longer incorrectly imply the app is running.

## 2.0.0-beta.46

- Added Fine spectrum with 180 slim radial bars, dotted baseline and bright tips.
- Added Particle sphere with 112 radial bars and a rotating, depth-shaded particle globe.
- Both styles support captured audio, adjustable accent colors, saved JSON widgets and reduced motion.

## 2.0.0-beta.45

- Add Album artwork colors for v3 progress bars, with smooth color blending and saved custom-color fallback. Cache bounded palettes extracted locally from the currently playing Spotify/YouTube cover.
- Add Circular bars, Circular wave and Flowing orb equalizer styles using the existing audio source, including Follow NextUp playback. Decorative mode remains available.
- Add Fit around album art and compact equalizer controls in Widget studio.
- Include Album-Aura.json as a ready-to-import example. Audio sources/account connections are not embedded in widget JSON.

## 2.0.0-beta.44

- Border lights now leave tapered, curved trails through their actual past canvas positions. Spinning or floating a shape no longer swings the whole tail as a rigid line.
- Smooth trail rendering uses quadratic curves, fading color and a small luminous tip. Bound history by travel distance/time, reset after suspended frames and respect reduced motion.
- Keep the beta.43 Miffy cloud/star preservation and preview fixes.

## 2.0.0-beta.43

- Preserve clouds and stars when converting v2 widgets to v3, saving, exporting and reopening.
- Use the same background-effect renderer in the editor, animation preview and browser source.
- Preview song transition no longer upgrades or changes the draft simply to display it.
- Existing Miffy JSON files retain their effects without adding clouds/stars controls.

## 2.0.0-beta.42

- Keep a Layers selector visible in Widget studio, including covered layers. Add Send to back / Bring to front and start new shapes behind existing content.
- Add Play/Stop layer motion directly on the editing canvas. Choosing a motion previews it immediately using simulated playback.
- Fix clipping of pulsing layers and make border lighting follow layer motion and opacity.
- Honor reduced-motion preferences with a visible editor explanation; treat motion amount zero as zero.

## 2.0.0-beta.41

- Add a compact Widget studio with saved-widget selection, JSON import, live preview and collapsible advanced controls.
- Preserve two to eight progress gradient colors in imported, saved and exported v3 JSON widgets.
- Add smooth arc-length border lighting attached to a shape layer, including editable colors and lap duration. Respect reduced motion.
- Ship Halo Orbit Glow and Automata Gradient as native JSON examples. No separate HTML widget installation is required.
- Correct the v3 editor progress preview and animation preview clock.
- Preserve existing accounts, queues and settings when installing over NextUp.

## 2.0.0-beta.40

- Retire the stopped outgoing song before loading fallback, so a failed playlist load retries fallback instead of resuming the completed request.
- Retry idle fallback after saving corrected settings, including Needs attention; preserve explicit Pause.
- Add Check saved playlist without playback or cursor changes; show loaded/allowed counts and playlist-specific Spotify access errors.
- Bound playlist scans to 500 entries, stop on empty pages, and handle null/deleted entries.
- Actual Spotify-account playback remains unverified in the build environment.

# Changelog

## 2.0.0-beta.39

- Owner additions from Home, Queue and search results are approved immediately, including unrated YouTube videos. Existing eligible owner requests awaiting review are repaired on startup; viewer moderation and content blocks remain active.
- Spotify queue integration now uses NextUp's managed order across both sources. Stage only the next eligible Spotify request and verify the native queue before consuming it; do not blindly retry ambiguous appends.
- Managed end detection now takes precedence over unrelated Spotify continuation, including when fallback is enabled.
- Add YouTube fallback playlists, a preferred-platform selector, paginated metadata loading, and independent persisted playlist positions for both services. Requests take precedence after the current fallback song.
- Default new installations to playlist order instead of shuffle. Existing shuffle preferences remain saved. Paused playback stays paused.

## 2.0.0-beta.38

- Pasted Spotify and YouTube track links now submit directly from Add a song, regardless of the name-search provider selection. The button changes to Add song for links.
- Successful requests clear the input and result cards; provider/input changes clear stale search results. Name searches still allow selecting a match.
- Show busy, success, empty-result and error messages beside the request form. Prevent duplicate submissions while a request is pending.
- Clarify that installer upgrades preserve each user's own userdata, while public build artifacts exclude account tokens and saved settings.

## 2.0.0-beta.37

- Mixed queues: detect YouTube media end immediately in the browser extension and hold the player against autoplay while the next source starts. Embedded YouTube uses the same local hold and faster command polling.
- Spotify: tighten polling only near managed track boundaries and pause from a fresh, verified playback state before an unrelated album/autoplay song can start. The boundary guard may trim up to 0.4 seconds; service/network latency can still leave a gap. Spotify native-queue mode is unchanged.
- Pause the outgoing source before loading a fallback playlist, and retain the current request if pause confirmation fails.
- Browser extension beta.10 is required for the browser-tab handoff fix. Replace/reload the unpacked extension and refresh the controlled YouTube tab after updating NextUp.

## 2.0.0-beta.36

- Ship a standalone NextUp product with no SongID or recognition engine/dependencies.
- Remove Account & Cloud navigation, client code, API routes and background polling.
- Use NextUp install/data paths, executable names, update assets and diagnostics.
- Fresh installations do not import older application data or account connections.
- Preserve Spotify/YouTube queues, Twitch rewards, role access, widgets, moderators,
  custom commands, equalizers, verified update support and the Ko-fi support link.
- Package only public project files and audit the source/installer payload for local
  data, credentials and private signing keys before distribution.
