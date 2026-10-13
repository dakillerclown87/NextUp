# NextUp architecture

- `studio.desktop`: native WebView2 window and local service lifecycle.
- `studio.server`: loopback admin API on 8888 and read-only widgets on 8889.
- `studio.chat_transport`: Twitch IRC connection, reply pacing and reconnects.
- `studio.twitch_service`: OAuth, roles and channel-point EventSub.
- `studio.providers`: Spotify/YouTube metadata and Spotify playback.
- `studio.playback`, `native_queue`, `fallback`: coordinated playback and queue modes.
- `studio.queue`: persisted requests, policy and redemption settlement ledger.
- `studio.moderation`: paired review access on 8890; optional separate HTTPS tunnel.
- `studio.widget_*`, `equalizer`: portable widget designs and local spectrum analysis.
- `studio.storage`: atomic local JSON writes, independent of recognition applications.
- `studio.updater`: signed updates anchored to publisher.json.

The standalone app has no recognition package or cloud-account client. New installs
use NextUp-specific storage and do not import another app's personal data.
