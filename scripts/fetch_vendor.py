"""Download the self-hosted files the site uses, so school networks that block other sites still work.

Run:  python scripts/fetch_vendor.py

- Fonts (Patrick Hand, Atkinson Hyperlegible; OFL licensed) -> static/fonts/   (already included in the repo)
- MediaPipe Tasks Vision (pinned version) + the face detector model -> static/vendor/mediapipe/
  (only needed for Phase 2 camera features; the site works fine without it)

If a download fails (no internet, blocked site), it prints a friendly note and keeps going.
"""
import _path  # noqa: F401

import io
import sys
import tarfile

import requests

from _path import ROOT

FONTS_DIR = ROOT / "static" / "fonts"
MP_DIR = ROOT / "static" / "vendor" / "mediapipe"
MEDIAPIPE_VERSION = "1.1.0"  # pinned on purpose; change it only after testing
NPM = "https://registry.npmjs.org"

FONT_PACKAGES = {
    "patrick-hand": ("@fontsource/patrick-hand", "5.3.0", ["patrick-hand-latin-400-normal.woff2"], "OFL-PatrickHand.txt"),
    "atkinson-hyperlegible": ("@fontsource/atkinson-hyperlegible", "5.3.0",
                              ["atkinson-hyperlegible-latin-400-normal.woff2", "atkinson-hyperlegible-latin-700-normal.woff2",
                               "atkinson-hyperlegible-latin-400-italic.woff2"], "OFL-AtkinsonHyperlegible.txt"),
}
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/"
             "float16/1/blaze_face_short_range.tflite")


def npm_tarball(package, version):
    name = package.split("/")[-1]
    url = f"{NPM}/{package}/-/{name}-{version}.tgz"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz")


def extract(tar, member_path, dest):
    """Copy one known file out of the tarball (never trusts paths inside the archive)."""
    f = tar.extractfile(f"package/{member_path}")
    if f is None:
        raise FileNotFoundError(member_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(f.read())


def fetch_fonts():
    ok = True
    for key, (package, version, files, license_name) in FONT_PACKAGES.items():
        if all((FONTS_DIR / f).exists() for f in files):
            print(f"  fonts: {key} already here")
            continue
        try:
            tar = npm_tarball(package, version)
            for f in files:
                extract(tar, f"files/{f}", FONTS_DIR / f)
            extract(tar, "LICENSE", FONTS_DIR / license_name)
            print(f"  fonts: downloaded {key}")
        except Exception as e:  # noqa: BLE001 - friendly message instead of a crash
            ok = False
            print(f"  fonts: couldn't download {key} ({type(e).__name__}). The site will use system fonts.")
    return ok


def fetch_mediapipe():
    try:
        tar = npm_tarball("@mediapipe/tasks-vision", MEDIAPIPE_VERSION)
        extract(tar, "vision_bundle.mjs", MP_DIR / "vision_bundle.mjs")
        for f in ("vision_wasm_internal.js", "vision_wasm_internal.wasm", "vision_wasm_nosimd_internal.js",
                  "vision_wasm_nosimd_internal.wasm"):
            extract(tar, f"wasm/{f}", MP_DIR / "wasm" / f)
        r = requests.get(MODEL_URL, timeout=60)
        r.raise_for_status()
        (MP_DIR / "blaze_face_short_range.tflite").write_bytes(r.content)
        (MP_DIR / "VERSION.txt").write_text(f"@mediapipe/tasks-vision {MEDIAPIPE_VERSION}\n", encoding="utf-8")
        print(f"  mediapipe: downloaded version {MEDIAPIPE_VERSION} + face detector model")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  mediapipe: couldn't download ({type(e).__name__}). Only Phase 2 camera features need it.")
        return False


def main():
    print("Fetching self-hosted files…")
    fonts_ok = fetch_fonts()
    mp_ok = fetch_mediapipe()
    print("Done." if fonts_ok and mp_ok else "Done (with notes above). The site still runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
