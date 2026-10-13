# Publishing your first release and future bug fixes

## Setup for dakillerclown87/NextUp

The repository address is configured. The public key remains blank until you
generate your own key and save the matching private key in GitHub Actions.
The GitHub connection used to prepare this change cannot manage Actions secrets.

1. Merge the source/publishing pull request. Download **Code → Download ZIP**
   from the repository and extract it on your Windows PC.
2. With NextUp installed, open PowerShell in the extracted source folder:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\configure-publisher.ps1
   ```

   The script uses NextUp's included Python runtime. It generates your key locally
   and fills in the public key in this folder's `publisher.json`. It does not
   print or upload the private key or replace a public key that already exists.
3. Open `%USERPROFILE%\.nextup-signing\private-key.txt` locally. Copy its text into
   [a new Actions repository secret](https://github.com/dakillerclown87/NextUp/settings/secrets/actions/new)
   named **NEXTUP_SIGNING_KEY**. Back up the private file securely.
4. Upload/commit **only the updated `publisher.json`** to `main`. Never upload the
   private-key file.
5. Open **Actions → Publish signed release → Run workflow** on `main`. A successful
   run creates a draft release containing the EXE, checksum and signed update
   archives. Review the draft under **Releases**, then publish it. A rerun will
   not replace an existing release's assets; use a new version for later fixes.
6. Install that first configured EXE over your current NextUp installation. This
   installs the trusted public key once while retaining settings. Old installers
   with a blank key cannot discover the update automatically.

Use a tag matching the source version exactly: **`v2.0.0-beta.64`**, including
the dot between `beta` and `64`. Do not attach a new EXE to an old version tag.
The existing `v2.0.0-beta61` release contains a beta.63 EXE but no signed update
archives, so it cannot serve as an in-app update release.

## One-time publisher setup

If NextUp says updates are not published/configured, the downloaded build has
no trusted GitHub repository and/or public signing key. This is publisher setup,
not a problem with your Spotify or Twitch account. Uploading just an EXE to a
release does not enable the signed updater. Until setup is complete, install a
newer official NextUp EXE over the existing installation; do not uninstall or
delete the user-data folder first.

1. Create your own empty GitHub repository. Upload this **source folder**, not
   `%LOCALAPPDATA%\NextUp`. Keep the included `.gitignore` and LICENSE.
2. In a development environment with requirements installed, run:

   `python tools/release.py --generate-key --repository YOURNAME/YOURREPO`

   This updates `publisher.json` with your public key/repo. The private key is
   saved outside the repository at `~/.nextup-signing/private-key.txt`.
3. Back up that private key securely. In GitHub → repository Settings → Secrets
   and variables → Actions, add **NEXTUP_SIGNING_KEY**, containing that file's
   base64 text. Never commit it, post it in chat, or put it in an application ZIP.
4. Commit `publisher.json` with only the public key. Preserve the public/private
   key pair across future releases. Installed clients pin this trust anchor.
   Its repository must be `YOURNAME/YOURREPO`, not a full URL. The repository
   needs to be public for this unauthenticated updater. The release workflow
   now validates the repository, key pair and version tag before building.
5. Review provider policies and licensing before distributing. Authorizing a
   Spotify app for your own account does not authorize unlimited public users.
6. Run the NextUp test suite and test the real Windows services using your accounts.
7. Set `studio/__init__.py` to the new version and increment the installer numeric version. Commit
   and push, then tag that commit, for example `v2.0.0-beta.39`, and push the tag.
8. The release workflow tests and builds the Windows EXE, then smoke-tests the
   bundled imports and silent installation. It signs the source update and
   Windows runtime update assets and creates a GitHub Release. GitHub Actions
   must be enabled and the signing secret present.
9. New users download `NextUp-Setup-<version>-x64.exe` and install it. No Python
   is required. Their copy now trusts your repository/public key for later updates.
   GitHub also provides the source; the EXE does not change the project's MIT license.

Because this delivered development ZIP has no publisher configured, testers
using it must receive your first configured build once. After that, the in-app
flow handles releases without another manual installer download.

To check publishing configuration locally without creating release files, open
PowerShell in the source folder with the development requirements installed:

```powershell
$env:NEXTUP_SIGNING_KEY = (Get-Content "$HOME/.nextup-signing/private-key.txt" -Raw).Trim()
python tools/release.py --check-publisher
Remove-Item Env:NEXTUP_SIGNING_KEY
```

Only the project owner performs this setup. Regular users never need a signing
key or a GitHub developer account. Do not send anyone your private key.

## What an installation or update keeps

Starting with the beta.64 installer, a successful component check and activation
automatically removes older version folders. It keeps the active version and
one previous version for the Start menu rollback shortcut. A staged pending
update is also protected until activation. Cleanup failures (for example a
locked old file) do not fail installation; the launcher retries at its next start.
Failed component checks leave the current version and existing version folders
alone. Invalid installation markers stop cleanup instead of guessing.

Settings, linked-account tokens, queued songs, widgets/backgrounds and overlay
keys remain in `%LOCALAPPDATA%\NextUp\userdata`. Cleanup only targets recognized
version folders under `%LOCALAPPDATA%\NextUp\versions`; it does not delete your
Downloads folder, installer EXEs or unrelated files. It does not reset settings
or copy the publisher's personal settings into users' installations.

This change lives in the stable bootstrap: existing users need this installer
once to receive cleanup support. Later signed app updates use that bootstrap
without reinstalling. Install into the same per-user location to keep settings.

## Shipping a fix

Edit the source, add a meaningful regression test, update CHANGELOG.md, bump the application and installer
versions (e.g. `2.0.0-beta.39`), commit/push and push its matching `v...`
tag. Users on the beta channel can check for it in Updates. Releases must have
the matching assets and valid signature: source clients use `nextup-app.zip`,
`manifest.json`, `manifest.sig`; EXE clients use `nextup-windows-x64.zip`,
`windows-manifest.json`, `windows-manifest.sig`. Publishing an ordinary commit
alone is not an application update.

`publisher.json` accepts `channel: "beta"` (includes prereleases) or `"stable"`
(excludes prereleases). Users do not automatically install unreviewed commits.
The channel/trust anchor is retained when staging a release.

The updater downloads only from GitHub release hosts, limits download/extracted
sizes, verifies Ed25519 and SHA-256, rejects unsafe ZIP paths and stages a new
version. It never edits user data. EXE updates include a complete private runtime and dependencies for each version;
no Python/pip installation runs on the user's machine. Source clients continue
using per-version virtual environments. The stable bootstrap itself is intentionally not overwritten
by these application updates; changing the minimum Python/bootstrap contract
requires a separately explained bootstrap upgrade.

For a manual local release build, run `python tools/build_windows.py` first, then load your private key into the environment
variable NEXTUP_SIGNING_KEY and run `python tools/release.py`. Do not paste
private keys into shell commands that will be saved in shell history.

No Windows Authenticode signing is configured. The EXE is unsigned; users may
see an unknown-publisher prompt. Ed25519 release verification is separate.
See WINDOWS-BUILD.md for the complete build process and runtime layout.

