# Application audio for widgets

Select **Follow NextUp playback** under Stream widgets → Equalizer audio →
Motion once for automatic operation. NextUp maps the current/starting provider
reported by its conductor to Spotify, the connected browser or its embedded player. A separate
capture task checks for source changes every half second without controlling
playback. Paused/failed/stopped playback clears capture; resume reconnects. A
missing or failed process is retried every five seconds with a fresh creation
time. Background discovery uses process-tree roots so minimized/tray apps work.
No manual source mapping is necessary; your existing YouTube player mode applies.
Ambiguous multiple roots are reported instead of guessed. Existing manual and
decorative choices are retained on upgrade. Saved follow mode starts at launch.

For manual operation, choose Manual application selection, then choose a visible
running application under Stream widgets → Equalizer audio.
Refresh applications, select it and click Use selected application. Retry capture
reopens the same process; refresh and re-select if the process has restarted in manual mode. Follow mode reconnects automatically.
Selecting Decorative animation stops the helper. A single source feeds every
widget, including OBS and inline previews. Show equalizer still controls whether
bars are visible on each design. This is a spectrum visualizer, not an audio EQ
that modifies playback.

Windows process loopback includes child processes and follows the selected app
across output devices. Open an app window if it is missing from the list. Browser
processes may include multiple tabs. Spotify must play locally, not solely on a
remote Spotify Connect device. Audio muting/protection and unsupported app paths
can result in silence; the panel reports waiting for audio instead of fake beats.
Use the sensitivity slider for quiet sources. Capture never falls back to a
microphone or desktop-wide mix. Manual mode needs re-selection after Spotify/Chrome restarts.

## Activation error 0x8000000e

Beta.16–18 had a callback initialization defect: the free-threaded completion
handler did not expose IAgileObject. Beta.19 adds that interface, preserves COM
identity and checks the callback interfaces before activation. This defect matches
the reported `Activate 0x8000000e` failure; actual Windows capture still needs
confirmation on the affected PC. Close NextUp, install beta.19 and retry capture.
Saved settings and connections are preserved; Spotify credentials do not need
to be reset. Follow mode retries automatically while playback is active.

## Connected browser detection (beta.18)

For external YouTube playback, the authenticated extension's local TCP peer port
comes from the server transport, never an extension-provided PID. The native
helper uses GetExtendedTcpTable to find the owning process and ascends same-app
parents to the browser root. It recognizes Chrome, Edge, Brave, Opera/GX, Vivaldi
and Firefox. Process creation times prevent reused parent PIDs being selected.
The connection is checked again before emitting the selected process identity.
An unresolved peer clears capture and retries, with no unrelated-browser fallback.
Peer information stays in memory and is not exposed to overlays. The loopback
connection remains authenticated and only valid extension origins can pair.

## Implementation

`packaging/windows/audio_capture.c` invokes ActivateAudioInterfaceAsync with
AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK and includes the selected process
tree. It validates PID plus process creation time, uses an agile COM callback,
and writes 48 kHz stereo signed 16-bit PCM to a private pipe. It watches both the
selected process and parent NextUp process and exits when either closes.

`studio/equalizer.py` uses a 4096-sample Hann window and FFT independently on both
channels, preserving opposite-phase content. Thirty-two logarithmic bands from
40 Hz to 18 kHz are mapped from -72..0 dB to normalized levels. The widget socket
sends only these levels, up to 20 updates/second. Browser interpolation provides
smooth attack/release and clears stale samples. No raw audio is stored or sent
to overlays. The default remains decorative animation until a source is chosen.

## Validation boundary

The native helper is cross-compiled with MinGW-w64. Tests cover generated audio
through the subprocess, FFT, WebSocket and actual browser bars, including silence,
switching, closure, stale identity, errors and saved preview/removal. These tests
do not execute Windows WASAPI. Actual app capture requires a Windows test; it
could not be run in the Linux build environment. No live provider accounts were
used or playback-management behavior changed in this release.

## Microsoft references

- https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getextendedtcptable

- https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/
- https://learn.microsoft.com/en-us/windows/win32/api/mmdeviceapi/nf-mmdeviceapi-activateaudiointerfaceasync
- https://learn.microsoft.com/en-us/windows/win32/api/audioclientactivationparams/ns-audioclientactivationparams-audioclient_activation_params

The process loopback API requires Windows build 20348 or later. NextUp presents
an unsupported message on older builds without stopping other widget functions.
