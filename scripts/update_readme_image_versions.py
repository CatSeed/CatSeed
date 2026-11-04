#!/usr/bin/env python3
"""Update README image URLs only when the published SVG content changes.

The query parameter is a short checksum of each generated image, making GitHub's
image proxy treat changed graphics as new assets without touching unchanged ones.
Only public SVG hashes are written; no private repository information is exposed.
"""
import hashlib
import re
from pathlib import Path

README = Path("README.md")
DIST = Path("dist")
IMAGE_NAMES = ("languages", "activity", "github-contribution-grid-snake")
BASE = "https://raw.githubusercontent.com/CatSeed/CatSeed/output/"


def main():
    original = README.read_text(encoding="utf-8")
    updated = original
    for name in IMAGE_NAMES:
        image = DIST / (name + ".svg")
        if not image.is_file():
            raise RuntimeError("Missing generated SVG: " + name)
        version = hashlib.sha256(image.read_bytes()).hexdigest()[:16]
        # Only change the src URL, and keep any surrounding image markup intact.
        pattern = re.compile(r'(?<=src=")' + re.escape(BASE + name + ".svg") +
                             r'(?:\?v=[a-zA-Z0-9._-]+)?(?=")')
        updated, matches = pattern.subn(BASE + name + ".svg?v=" + version, updated)
        if matches != 1:
            raise RuntimeError("Expected one image reference in README for: " + name)
    if updated != original:
        README.write_text(updated, encoding="utf-8")
        print("README image versions updated to match generated SVG content.")
    else:
        print("README image versions unchanged.")


if __name__ == "__main__":
    main()
