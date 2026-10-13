# Event Horizon — NextUp widget

Requires NextUp 2.0.0-beta.28 or later. No Python installation needed with the EXE.

1. Close NextUp and install beta.28.
2. Stream widgets → Add widget → select Event-Horizon.nextup.json.
3. Save as new widget. Its own saved preview and remove control appear with the
   other saved widgets. The designer shows the fully expanded card for editing.
4. Copy the saved widget URL to an OBS Browser Source at 1120 × 420, 60 FPS.
   Keep NextUp running. Leave the Browser Source background transparent.

The preset does not replace your existing widgets. Colors, hex codes, fonts,
artwork size and element positions remain editable. Artwork, song, artist,
requester and progress come from NextUp; long titles scroll. There is no NextUp
wordmark or decorative equalizer. It works with either Spotify or YouTube state.

The final four seconds of a known song duration draw the card into the event
horizon. It waits as a small glowing black hole when playback is empty or waiting
for the next provider. A confirmed next song produces a 1.7 second warm shockwave
and expanding card. A manual skip uses an accelerated pull-in. A paused song
holds its progress; seeking backward restores the card. Unknown durations wait
for an actual track change. Reduced-motion preferences use instant changes.

Transitions depend on NextUp's reported playback, polled every 1.5 seconds and
interpolated between updates. A provider reporting an inaccurate ending can make
an effect early or late. This widget never starts, stops or changes your audio.
The effects are artistic cinematic interpretation, not a physics simulation.

The MP4 is a demonstration recorded from the real widget renderer with simulated
playback, sample titles and fixture album artwork. Actual frame rate depends on
OBS/browser hardware. Native Windows installation and OBS are not run on this
Linux build host. No billing, payment unlock or premium licensing is implemented.

## Artwork provenance / source

Generated with the image-generation skill for this widget. Project asset:
`studio/static/event-horizon.png` (copied unchanged from generated output
`exec-4dffc12a-fa7a-44c4-9769-174dff5d81f8.png`). The runtime composites the black
matte into emission alpha for transparent overlays; it contains no remote asset
or external font dependency. Preview album artwork is a local SVG test fixture.

Prompt: cinematic physically inspired photorealistic black hole VFX texture;
centered pitch-black event horizon, ivory/gold accretion disk seen nearly edge-on,
gravitational lensing arch and underside arc, pure black margins, no text or UI,
subtle restrained bloom, fine turbulent filaments and realistic cinematic look.

Source: `studio/static/widget-singularity.js` (animation),
`studio/static/widget-renderer.js` (live card), `studio/static/overlay.html`
(playback snapshots), and `docs/Event-Horizon.nextup.json` (portable design).
