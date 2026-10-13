# beta.60 playback verification

## Confirmed cause

The captured Spotify catalog response resolved original track ID
`21JvBMXPGJ6rpvHacAFWUO` to playable ID `6kabsWWWUCKCXbBSPt4Cae`,
with the original ID present in `linked_from`. Both representations had
ISRC `CA6D21700255`, the same artist IDs, duration 233647 ms, and explicit=false.
The old playback check treated this permanent identity difference as a failed
start even though Spotify was playing the requested recording.

The public catalog-only fixture is in `tests_studio/fixtures/spotify_stay_relink.json`.
No account credentials or private diagnostic exports are included.

## Changes verified

- Confirm Spotify relinking through read-only metadata, retaining original
  playlist cursor identity and accepting the verified playable identity.
- Require strong recording metadata when an explicit relink is unavailable.
- Preserve existing playback progress instead of restarting a confirmed song.
- Clear resolved recovery state and limit unresolved same-device recovery.
- Follow the playlist currently playing in Spotify without importing it into
  the viewer request queue. Requests take precedence and return to that context.

## Validation

The release source passed 364 Python tests and 27 JavaScript tests, including
permanently different IDs, six successive relinked skips, sparse metadata,
identity rejection guards, 15 natural playlist transitions, playlist changes,
viewer request return, and simulated YouTube handoffs.

The user ran the isolated desktop test build and confirmed all three requested
live scenarios: six or more skips, natural song endings, and a requested song
followed by return to the Spotify playlist. The release retains that tested
playback implementation; the release version and documentation were updated.

Earlier synthetic skip tests eventually returned the expected ID and therefore
did not reproduce permanent relinking. Those counts are not evidence that every
Spotify environment works. Native Windows installer execution and live YouTube
handoffs were not independently verified in the build environment.

## Using the mode after installation

Close NextUp and the isolated test launcher, then install over the existing app.
Existing user settings remain in their separate data directory. Test-launcher
settings are not copied to the installed app.

In Queue → Playlist playback, enable **Follow Spotify's current playlist**.
Start the desired playlist in Spotify on the selected device. This disables
saved fallback playback while retaining its saved link for later use.

## Reproduce automated checks

```sh
python -m unittest discover -s tests_studio -q
node --test tests_js/*.test.cjs
python tools/audit_distribution.py
```
