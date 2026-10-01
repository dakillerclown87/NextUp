# Contributing

Use Python 3.13 in a virtual environment and install requirements.txt. Run
`python -m unittest discover -s tests_studio -v` before submitting a change.

Keep provider calls behind adapters, preserve queue ownership/role checks, and
add a regression test for changes affecting playback, refunds, auth or updates.
Do not commit real credentials, account data, logs, databases or signing keys.
Keep public overlays read-only and separate from the admin service.

No app/plugin should receive general chat logging by default. That feature is
intentionally deferred. Document any data-retention changes before implementing.

Use the existing MIT license and include third-party attribution where needed.
Bump versions and document behavior changes in CHANGELOG.md for releases. See
docs/PUBLISHING.md for the signing and release process.
