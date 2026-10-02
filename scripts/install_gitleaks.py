"""Install the pinned official binary after checking its committed SHA-256."""

import hashlib
import io
import json
import platform
import shutil
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    tool = json.loads((ROOT / ".ci/tools.json").read_text())["gitleaks"]
    system = {"Windows": "windows", "Linux": "linux"}.get(platform.system())
    if not system or platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit(
            "Installer supports Windows/Linux x64; use the pinned upstream release on other hosts"
        )
    suffix = "zip" if system == "windows" else "tar.gz"
    asset = f"gitleaks_{tool['version']}_{system}_x64.{suffix}"
    url = f"https://github.com/gitleaks/gitleaks/releases/download/v{tool['version']}/{asset}"
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read(100 * 1024 * 1024 + 1)
    if (
        len(data) > 100 * 1024 * 1024
        or hashlib.sha256(data).hexdigest() != tool["assets"][asset]
    ):
        raise SystemExit("Gitleaks download checksum mismatch")
    executable = "gitleaks.exe" if system == "windows" else "gitleaks"
    target = ROOT / ".ci/bin" / executable
    target.parent.mkdir(parents=True, exist_ok=True)
    # Extract only the named executable; never extract archive paths wholesale.
    if suffix == "zip":
        with (
            zipfile.ZipFile(io.BytesIO(data)) as archive,
            archive.open(executable) as source,
            target.open("wb") as output,
        ):
            shutil.copyfileobj(source, output)
    else:
        with (
            tarfile.open(fileobj=io.BytesIO(data)) as archive,
            target.open("wb") as output,
        ):
            source = archive.extractfile(executable)
            if source is None:
                raise SystemExit("Missing Gitleaks executable")
            with source:
                shutil.copyfileobj(source, output)
    target.chmod(0o755)
    print("Installed checksum-verified Gitleaks " + tool["version"])


if __name__ == "__main__":
    main()
