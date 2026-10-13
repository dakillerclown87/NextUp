# Repeated-skip regression report

## Evidence

The supplied beta.58 diagnostics recorded eight wrong-track recovery events and one deferred playlist song. The last report said playback was running on the intended device, but the expected track did not match. The export did not contain the two track IDs or playlist-context match, so it cannot establish exactly what Spotify was reporting. The patch records those fields for future diagnosis.

## Failing reproductions before the fixes

- The real Spotify adapter is connected to a simulated player that accepts the first context loads but keeps the previous track after subsequent loads. Starting the playlist then skipping twice raises spotify_wrong_track with beta.58.
- Starting a playlist target already playing at 23 seconds sends another position-zero command under beta.58.
- During pending fallback recovery, the launcher Skip API route selects the retained song again (p1 instead of p2). The route-level test failed before its correction.

The simulated provider behavior is a controlled reproduction consistent with the error, not a recording of the user's Spotify session.

## Passing release checks

- 1,000 consecutive skips through the actual launcher HTTP route, real conductor and real Spotify adapter. Each resulting item matches the expected sequence; the playlist is fetched once and context reloads do not grow with skips.
- Delayed reports after the second native skip: playback remains at 12 seconds, the skip is not repeated, and late confirmation clears the error.
- Delayed playlist-offset confirmation: playback remains at 17.5 seconds with no additional control writes.
- An already-playing song stays at 23 seconds; restoring its playlist context preserves a 42-second position.
- Repeated clicks during a pending operation emit one skip only.
- Two skips followed by YouTube and a viewer Spotify request preserve priority and return to the saved playlist, then continue through ten more skips.
- Pause stops audio while confirmation is pending; explicit Skip abandons the pending background song via the launcher API.
- Wrong-context and wrong-device reports are not accepted as success.
- 337 Python tests and 27 JavaScript tests passed before packaging.

## Reproduce

From the source folder after installing development requirements:

```powershell
$env:NEXTUP_SKIP_SOAK = "1000"
python -m unittest discover -s tests_studio -p test_repeated_skips.py -v
python -m unittest discover -s tests_studio -q
node --test tests_js/*.test.cjs
```

These tests use simulated provider responses, never credentials or live accounts. Native Windows execution and live Spotify playback were not available in the build environment. An acknowledged command whose state never becomes valid remains visible for owner action instead of being automatically resent.

## Provider references

- [Skip to next](https://developer.spotify.com/documentation/web-api/reference/skip-users-playback-to-next-track)
- [Start/resume playback](https://developer.spotify.com/documentation/web-api/reference/start-a-users-playback)

Spotify documents that ordering is not guaranteed when mixing Player API commands. NextUp therefore verifies the native queue before skipping and does not repeat an acknowledged command just because its report is delayed.
