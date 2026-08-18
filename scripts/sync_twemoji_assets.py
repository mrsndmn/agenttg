#!/usr/bin/env python3
"""Refresh the vendored twemoji SVGs under ``src/agenttg/assets/twemoji/svg``.

The PNG table renderer substitutes emoji offline from these assets, so they are
checked in rather than fetched at render time.  Re-run this when you want a newer
twemoji release:

    python scripts/sync_twemoji_assets.py [--version 15.0.0]

Assets come from the ``@twemoji/svg`` npm package (one tarball, ~1.5 MB), whose
graphics are CC-BY 4.0.  The tarball's licence file is vendored alongside them.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

REGISTRY = "https://registry.npmjs.org/@twemoji/svg"
ASSETS = Path(__file__).resolve().parent.parent / "src" / "agenttg" / "assets" / "twemoji"


def _resolve_tarball(version: str | None) -> tuple[str, str]:
    with urllib.request.urlopen(REGISTRY, timeout=60) as resp:
        meta = json.load(resp)
    version = version or meta["dist-tags"]["latest"]
    if version not in meta["versions"]:
        sys.exit(f"unknown @twemoji/svg version {version!r}")
    return version, meta["versions"][version]["dist"]["tarball"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="@twemoji/svg version (default: latest)")
    args = parser.parse_args()

    version, url = _resolve_tarball(args.version)
    print(f"fetching @twemoji/svg {version} from {url}")
    with urllib.request.urlopen(url, timeout=300) as resp:
        blob = resp.read()

    svg_dir = ASSETS / "svg"
    if svg_dir.exists():
        shutil.rmtree(svg_dir)
    svg_dir.mkdir(parents=True)

    count = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar.getmembers():
            name = Path(member.name).name
            if member.isfile() and name.endswith(".svg"):
                data = tar.extractfile(member)
                if data is not None:
                    (svg_dir / name).write_bytes(data.read())
                    count += 1
            elif member.isfile() and name.lower() in ("license", "license-graphics"):
                data = tar.extractfile(member)
                if data is not None:
                    (ASSETS / "LICENSE-GRAPHICS").write_bytes(data.read())

    print(f"wrote {count} SVGs to {svg_dir}")
    if not count:
        sys.exit("no SVGs found in the tarball -- did the package layout change?")


if __name__ == "__main__":
    main()
