# Show NextUp badges on GitHub and in the app

The small labels in the reference image are live status badges, not part of the installer. Shields.io can turn public GitHub release, download, license, and Actions data into badge images.

## GitHub README

1. Open your repository on GitHub.
2. Open `README.md`, choose the pencil (Edit), and paste the block below beneath the title.
3. Replace every `OWNER/REPO` with your actual GitHub username and repository name (for example, `your-name/NextUp`).
4. Choose Preview, then Commit changes.

```markdown
[![Release](https://img.shields.io/github/v/release/OWNER/REPO?include_prereleases&sort=date)](https://github.com/OWNER/REPO/releases)
[![Release asset downloads](https://img.shields.io/github/downloads/OWNER/REPO/total)](https://github.com/OWNER/REPO/releases)
[![Tests](https://github.com/OWNER/REPO/actions/workflows/check.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/check.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Support on Ko-fi](https://img.shields.io/badge/Support-Ko--fi-ff5e5b)](https://ko-fi.com/nextupplus)
```

The release badge includes beta prereleases. Publish your EXE as an asset on a GitHub Release to make release/download data available. The total download badge counts release-asset downloads, including repeat downloads and other assets; it is not a count of people, installations, daily users, or monthly users. The Tests badge uses this project's `check.yml` workflow; let the workflow finish before expecting a result. NextUp's current source license is MIT, not the GPLv3 badge in the reference image.

An `inaccessible` badge means its underlying data could not be read. Check the repository/endpoint address, visibility and service availability; do not replace it with an invented number.

## Song requests and active users

These are not GitHub metrics. NextUp currently has no global public request/active-user counter. Each user's local queue/history cannot tell you how many people are using other installations.

To add those counters later, deploy a small statistics service (for example, a Cloudflare Worker backed by D1) and add an explicit optional analytics setting in the desktop app. With permission, clients can send aggregate request increments and a random installation identifier's activity heartbeat. Do not send account tokens, Twitch usernames, song names, or chat messages for this purpose. Define the metrics clearly: daily active installations over a UTC day, monthly active installations over a calendar month, and accepted viewer requests excluding fallback playback. Random installation identifiers count installations, not verified unique people; reinstalling can create a new identifier. Deduplicate event IDs server-side and limit submissions to reduce double counting and abuse.

Publish only aggregate results. Shields.io's endpoint badge accepts JSON with `schemaVersion`, `label`, `message`, and `color`; have the server fill `message` from the actual aggregate. Keep submission credentials and private records out of the public endpoint. Show Unavailable when it cannot be read, not a made-up zero.

## Inside NextUp

An About/Project statistics panel can display the same public aggregate endpoint and GitHub release data as text or badges. Fetch outside the playback loop, cache it, and show when it last updated so an unavailable statistics service cannot delay music. This release documents that integration; it does not enable telemetry or deploy a statistics backend.

Repository-specific badge URLs need your repository's public URL. The Ko-fi and MIT badges already work without one and are included in the README.

## References

- [Shields.io introduction](https://shields.io/docs/)
- [GitHub release download badge](https://shields.io/badges/git-hub-downloads-all-assets-all-releases)
- [Custom endpoint badges](https://shields.io/badges/endpoint-badge)
- [GitHub workflow status badges](https://docs.github.com/en/actions/how-tos/monitor-workflows/add-a-status-badge)
