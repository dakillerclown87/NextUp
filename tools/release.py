"""Build the update assets from a reviewed source tree; sign with Ed25519."""

import argparse, base64, hashlib, json, os, sys, zipfile
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PrivateFormat,
    PublicFormat,
    NoEncryption,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studio import __version__
from studio.update_publisher import validate_publisher


def files():
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT)
        if rel.parts[0] not in (
            "chrome-extension",
            "studio",
            "tests_studio",
            "tests_js",
            "tests_native",
            "tools",
            "docs",
            ".github",
            "vendor",
            "packaging",
        ) and not (len(rel.parts) == 1 and p.name in {
            "README.md", "LICENSE", ".gitignore", "publisher.json", "bootstrap.py",
            "requirements.txt", "requirements-windows.lock", "CHANGELOG.md",
            "SECURITY.md", "PRIVACY.md", "CONTRIBUTING.md", "VALIDATION-STUDIO.md",
        }        ):
            continue
        if (
            not p.is_file()
            or any(
                x.startswith(".venv")
                or x
                in (
                    "__pycache__",
                    "node_modules",
                    ".wrangler",
                    ".git",
                    "dist",
                    "build",
                    "userdata",
                    "data",
                    "signing-keys",
                )
                for x in rel.parts
            )
            or p.name.startswith((".dev.vars.", ".env."))
            or p.suffix.lower() in (".pyc", ".pem", ".key", ".pfx", ".p12", ".log", ".sqlite3", ".db")
            or p.name
            in (
                "config.json",
                ".dev.vars",
                ".env",
                "accounts.json", "studio.json", "tokens.json", "twitch_tokens.json",
                "chrome-pairing.json", "moderators.json", "cloud-settings.json",
                "overlay-key.txt", "admin-token.txt", "credentials.json",
                "before-cloud-restore.json",
                "queue.sqlite3",
                "private-key.txt",
                ".ready",
            )
        ):
            continue
        yield p, rel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate-key", action="store_true")
    parser.add_argument("--repository")
    parser.add_argument("--check-publisher", action="store_true",
                        help="Validate repository, public/private signing keys and release tag without building.")
    a = parser.parse_args()
    pub = json.loads((ROOT / "publisher.json").read_text())
    if a.generate_key:
        if pub.get("public_key"):
            raise SystemExit("publisher.json already pins a signing key. Restore the matching private key; do not replace the public key for installed users.")
        # Reject incomplete setup before creating any private signing material.
        repo = a.repository or pub.get("repository", "")
        validate_publisher({**pub, "repository": repo, "public_key": base64.b64encode(bytes(32)).decode()})
        folder = Path.home() / ".nextup-signing"
        folder.mkdir(mode=0o700, exist_ok=True)
        path = folder / "private-key.txt"
        if path.exists():
            raise SystemExit(
                "Signing key already exists. Preserve it; never generate a replacement casually."
            )
        key = Ed25519PrivateKey.generate()
        path.write_text(
            base64.b64encode(
                key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
            ).decode()
        )
        path.chmod(0o600)
        public = base64.b64encode(
            key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode()
        pub["public_key"] = public
        pub["repository"] = repo
        (ROOT / "publisher.json").write_text(json.dumps(pub, indent=2) + "\n")
        print(
            "Public key saved to publisher.json. Private key saved outside the repository at:",
            path,
        )
        return
    if a.repository:
        raise SystemExit("Use --repository with --generate-key for initial setup; preserve the publisher for later releases.")
    validate_publisher(pub, os.environ.get("GITHUB_REPOSITORY"))
    raw = os.environ.get("NEXTUP_SIGNING_KEY", "")
    if not raw:
        raise SystemExit(
            "Set NEXTUP_SIGNING_KEY from your private signing key file or GitHub Actions secret."
        )
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw, validate=True))
    public = base64.b64encode(
        key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()
    if public != pub["public_key"]:
        raise SystemExit("The signing key does not match publisher.json.")
    if (
        os.environ.get("GITHUB_REF_TYPE") == "tag"
        and os.environ.get("GITHUB_REF_NAME") != "v" + __version__
    ):
        raise SystemExit("Tag and studio.__version__ differ.")
    if a.check_publisher:
        print("Publisher and signing key verified for " + pub["repository"] + ". No files changed.")
        return
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    archive = out / "nextup-app.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p, rel in sorted(files()):
            z.write(p, rel.as_posix())
    data = archive.read_bytes()
    manifest = json.dumps(
        {
            "version": __version__,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    (out / "manifest.json").write_bytes(manifest)
    (out / "manifest.sig").write_bytes(base64.b64encode(key.sign(manifest)))
    windows = out / "nextup-windows-x64.zip"
    if windows.exists():
        with zipfile.ZipFile(windows) as z:
            bundle = json.loads(z.read("bundle.json"))
        if bundle["version"] != __version__ or bundle["platform"] != "windows-x64":
            raise SystemExit("Windows bundle version mismatch; rebuild the installer.")
        data = windows.read_bytes()
        manifest = json.dumps({"version": __version__, "platform": "windows-x64",
            "format": 1, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()},
            sort_keys=True, separators=(",", ":")).encode()
        (out / "windows-manifest.json").write_bytes(manifest)
        (out / "windows-manifest.sig").write_bytes(base64.b64encode(key.sign(manifest)))
    print("Built signed release:", __version__)


if __name__ == "__main__":
    main()
