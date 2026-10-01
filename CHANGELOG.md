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
