"""Opt-in signed GitHub releases. Stage new versions without replacing user data."""

import base64, hashlib, io, json, os, re, shutil, stat, zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from packaging.version import Version
from . import __version__
from .settings import ROOT, HOME
from .storage import write_private
from .update_publisher import validate_publisher

MAX_ARCHIVE = 40 * 1024 * 1024
WINDOWS_ASSETS = ("nextup-windows-x64.zip", "windows-manifest.json", "windows-manifest.sig")
SOURCE_ASSETS = ("nextup-app.zip", "manifest.json", "manifest.sig")


def verify(manifest, signature, archive, public_key):
    Ed25519PublicKey.from_public_bytes(
        base64.b64decode(public_key, validate=True)
    ).verify(base64.b64decode(signature, validate=True), manifest)
    info = json.loads(manifest)
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?", info["version"]):
        raise ValueError("Invalid release version.")
    if (
        hashlib.sha256(archive).hexdigest() != info["sha256"]
        or len(archive) != info["size"]
    ):
        raise ValueError("Update checksum/size mismatch.")
    return info


def unpack(archive, dest, bundled=False):
    dest = Path(dest)
    seen = set()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        if (
            len(z.infolist()) > (20000 if bundled else 2000)
            or sum(i.file_size for i in z.infolist()) > (600 if bundled else 100) * 1024 * 1024
        ):
            raise ValueError("Update archive exceeds limits.")
        for i in z.infolist():
            p = PurePosixPath(i.filename)
            name = i.filename
            if (
                p.is_absolute()
                or "\\" in name
                or ":" in name
                or any(
                    part in ("..", ".", "")
                    or part.rstrip(" .") != part
                    or part.split(".")[0].upper()
                    in {
                        "CON",
                        "PRN",
                        "AUX",
                        "NUL",
                        *[f"COM{x}" for x in range(10)],
                        *[f"LPT{x}" for x in range(10)],
                    }
                    for part in p.parts
                )
            ):
                raise ValueError("Unsafe archive path.")
            if name.lower() in seen or stat.S_ISLNK(i.external_attr >> 16):
                raise ValueError("Unsafe archive entry.")
            seen.add(name.lower())
            if p.parts[0].lower() in ("userdata", ".git", ".venv", "config.json"):
                raise ValueError("Release contains user data.")
        if not {"studio/__init__.py", "studio/server.py", "requirements.txt"} <= seen:
            raise ValueError("Incomplete application release.")
        if bundled and not {"runtime/python.exe", "runtime/python313.dll", "entry.py", "bundle.json"} <= seen:
            raise ValueError("Incomplete Windows bundle.")
        for i in z.infolist():
            target = dest / Path(i.filename)
            if i.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(i))


class Updater:
    def __init__(self, session, root=ROOT, home=HOME):
        self.session, self.root, self.home = session, Path(root), Path(home)
        self.product = "nextup"
        bundle = self.root / "bundle.json"
        if bundle.exists():
            self.product = json.loads(bundle.read_text()).get("product", "nextup")
        self.windows_assets = WINDOWS_ASSETS
        self.release = None
        self.busy = False
        self.bundled = os.environ.get("NEXTUP_BUNDLED") == "1"
        path = self.root / "publisher.json"
        self.publisher = json.loads(path.read_text()) if path.exists() else {}

    @property
    def configuration_error(self):
        try:
            validate_publisher(self.publisher)
        except ValueError as error:
            return str(error)
        return ""

    async def get(self, url, limit):
        for _ in range(5):
            p = urlsplit(url)
            if (
                p.scheme != "https"
                or p.hostname
                not in (
                    "api.github.com",
                    "github.com",
                    "release-assets.githubusercontent.com",
                    "objects.githubusercontent.com",
                )
                or p.username
            ):
                raise ValueError("Untrusted update download location.")
            async with self.session.get(
                url,
                allow_redirects=False,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "NextUp-Updater",
                },
            ) as r:
                if r.status in (301, 302, 303, 307, 308):
                    url = r.headers["Location"]
                    continue
                if r.status != 200:
                    raise ValueError(f"GitHub update check failed (HTTP {r.status}).")
                out = bytearray()
                async for chunk in r.content.iter_chunked(65536):
                    out.extend(chunk)
                    if len(out) > limit:
                        raise ValueError("Update download exceeds limit.")
                return bytes(out)
        raise ValueError("Too many download redirects.")

    async def check(self):
        self.release = None
        validate_publisher(self.publisher)
        repo = self.publisher.get("repository", "")
        releases = json.loads(
            await self.get(f"https://api.github.com/repos/{repo}/releases", 1_000_000)
        )
        releases = [
            r
            for r in releases
            if not r["draft"]
            and (self.publisher.get("channel") == "beta" or not r["prerelease"])
        ]
        for r in releases:
            try:
                version = Version(r["tag_name"].removeprefix("v"))
            except Exception:
                continue
            if version <= Version(__version__):
                continue
            assets = {x["name"]: x["browser_download_url"] for x in r["assets"]}
            if not set(self.windows_assets if self.bundled else SOURCE_ASSETS) <= assets.keys():
                continue
            for url in assets.values():
                if not url.startswith(f"https://github.com/{repo}/releases/download/"):
                    raise ValueError("Unexpected release asset URL.")
            self.release = {
                "version": str(version),
                "tag": r["tag_name"].removeprefix("v"),
                "notes": r.get("body", "")[:12000],
                "assets": assets,
            }
            return {k: v for k, v in self.release.items() if k != "assets"}
        self.release = None
        return {"version": __version__, "notes": "You are up to date."}

    async def stage(self):
        if self.busy:
            raise ValueError("An update is already being downloaded.")
        if not self.release:
            raise ValueError("Check for updates first.")
        self.busy = True
        temp = self.home / "staging-download"
        try:
            a = self.release["assets"]
            arc_name, manifest_name, sig_name = self.windows_assets if self.bundled else SOURCE_ASSETS
            manifest = await self.get(a[manifest_name], 65536)
            sig = await self.get(a[sig_name], 1024)
            archive = await self.get(a[arc_name], 160 * 1024 * 1024 if self.bundled else MAX_ARCHIVE)
            info = verify(manifest, sig, archive, self.publisher["public_key"])
            if info.get("product", "nextup") != self.product:
                raise ValueError("This update is for a different application.")
            if self.bundled and (info.get("platform") != "windows-x64" or info.get("format") != 1):
                raise ValueError("Incompatible Windows release.")
            if Version(info["version"]) != Version(self.release["tag"]) or Version(
                info["version"]
            ) <= Version(__version__):
                raise ValueError("Release version mismatch or downgrade.")
            if temp.exists():
                shutil.rmtree(temp)
            unpack(archive, temp, bundled=self.bundled)
            if self.bundled:
                metadata = json.loads((temp / "bundle.json").read_text())
                if metadata.get("product", "nextup") != self.product:
                    raise ValueError("Bundle product mismatch.")
            # Updates cannot replace the publisher trust anchor.
            publisher = dict(self.publisher)
            write_private(temp / "publisher.json", publisher)
            dest = self.home / "versions" / info["version"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                raise ValueError("This update is already staged or installed.")
            temp.rename(dest)
            write_private(self.home / "pending.json", {"version": info["version"]})
            return {
                "message": "Update verified and staged. Exit the app, then reopen the installed launcher to apply it."
            }
        finally:
            self.busy = False
            if temp.exists():
                shutil.rmtree(temp)
