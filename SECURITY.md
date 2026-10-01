# Security and reporting

Use GitHub's private vulnerability reporting after the repository owner enables
it. Do not post tokens, user-data files, private signing keys or unredacted logs
in public issues. This unreleased project has no assigned security contact yet.

The dashboard binds only to 127.0.0.1:8888. Every admin API request needs a random
per-process header key; origins and Host are checked and mutation routes use
POST. The key enters the browser in a fragment, which is removed after loading.
There are no admin routes on the read-only overlay server (127.0.0.1:8889).
Do not reverse-proxy/tunnel the admin port or disable these checks.

Spotify OAuth uses PKCE, random state, expiration and exact loopback redirect.
Twitch uses Public-client device authorization. Token refresh data is persisted
locally; no embedded app secrets are distributed. Twitch channel-owner scopes
cannot be replaced by a moderator badge. Queue metadata is always resolved on
the server; client-submitted song lengths/roles are not trusted.

Release verification pins a publisher Ed25519 public key and checks the archive
hash/size and safe extraction paths. A publisher signature authenticates the
publisher; it is not a malware scan. Only publish reviewed code. Compromise of
the signing key requires a deliberate trust-anchor migration.

Beta review still required: live Windows DPAPI, external account authorization,
real device timing, Twitch EventSub recovery, OBS/custom widgets and update
installation. See the validation record for executed checks and limitations.
