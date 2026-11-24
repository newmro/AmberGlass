#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rozpakowuje archiwa ze zdjęciami Amber Glass do images/.

Nazwy plików są znormalizowane (małe litery, bez spacji i polskich znaków).
Pliki PNG są zapisywane jako JPG. Duplikaty o tej samej treści są pomijane.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

from PIL import Image, ImageOps

SKIP_PREFIXES = ("__MACOSX",)
SKIP_FILE_PREFIXES = ("._",)


def decode_zip_name(info: zipfile.ZipInfo) -> str:
    name = info.filename
    if info.flag_bits & 0x800:
        return name
    try:
        return name.encode("cp437").decode("utf-8")
    except UnicodeDecodeError:
        return name


def should_skip(name: str) -> bool:
    parts = name.replace("\\", "/").split("/")
    if any(p in SKIP_PREFIXES for p in parts):
        return True
    base = parts[-1]
    if not base or base.startswith(SKIP_FILE_PREFIXES):
        return True
    if name.endswith("/"):
        return True
    return False


def slugify(filename: str) -> str:
    base = os.path.basename(filename)
    stem, _ext = os.path.splitext(base)
    stem = unicodedata.normalize("NFC", stem)
    trans = str.maketrans(
        {
            "ą": "a",
            "ć": "c",
            "ę": "e",
            "ł": "l",
            "ń": "n",
            "ó": "o",
            "ś": "s",
            "ź": "z",
            "ż": "z",
            "Ą": "a",
            "Ć": "c",
            "Ę": "e",
            "Ł": "l",
            "Ń": "n",
            "Ó": "o",
            "Ś": "s",
            "Ź": "z",
            "Ż": "z",
            "&": "",
            ":": "-",
        }
    )
    stem = stem.translate(trans)
    stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    stem = stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem)
    stem = re.sub(r"-{2,}", "-", stem).strip("-")
    return stem or "image"


def unique_name(dest_dir: Path, slug: str, used: set[str]) -> str:
    candidate = f"{slug}.jpg"
    n = 2
    while candidate in used or (dest_dir / candidate).exists():
        candidate = f"{slug}-{n}.jpg"
        n += 1
    used.add(candidate)
    return candidate


def file_md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def to_jpeg_bytes(data: bytes, original_name: str) -> bytes:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        img = background.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")
    ext = os.path.splitext(original_name)[1].lower()
    # Istniejące JPG zostawiamy bez ponownego kodowania — tylko transpozycja EXIF,
    # gdy była konieczna. Jeśli obraz nie był obracany i to już JPG, zwróć oryginał.
    if ext in {".jpg", ".jpeg"} and img.getexif() is not None:
        # Po exif_transpose dane mogły się zmienić; bezpieczniej zapisać, gdy tryb się zgadza.
        pass
    if ext in {".jpg", ".jpeg"}:
        # Zachowaj oryginalne bajty, jeśli otwarcie nie wymagało konwersji trybu
        # i nie było przezroczystości. Ponowne kodowanie dużych plików obniżyłoby jakość.
        try:
            original = Image.open(io.BytesIO(data))
            if original.mode == "RGB" and ImageOps.exif_transpose(original).size == original.size:
                # Brak konieczności obrotu — zostaw oryginał.
                orientation = original.getexif().get(274) if original.getexif() else None
                if orientation in (None, 1):
                    return data
        except Exception:
            pass
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92, optimize=True, subsampling=0)
    return out.getvalue()


def extract_zips(zips: list[Path], dest: Path, manifest_path: Path) -> list[dict]:
    dest.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = []

    hash_to_name = {}
    used = set()
    for rec in manifest:
        name = rec.get("file")
        digest = rec.get("md5")
        if name:
            used.add(name)
        if name and digest:
            hash_to_name[digest] = name

    for existing in dest.glob("*.jpg"):
        used.add(existing.name)
        if existing.name not in {r.get("file") for r in manifest}:
            digest = file_md5(existing.read_bytes())
            hash_to_name.setdefault(digest, existing.name)

    for zip_path in zips:
        print(f"Rozpakowuję {zip_path.name}", flush=True)
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                raw_name = decode_zip_name(info)
                if should_skip(raw_name):
                    continue
                ext = os.path.splitext(raw_name)[1].lower()
                if ext not in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}:
                    print(f"  pomijam (nie obraz): {raw_name}")
                    continue
                data = zf.read(info)
                try:
                    jpeg = to_jpeg_bytes(data, raw_name)
                except Exception as exc:
                    print(f"  BŁĄD konwersji {raw_name}: {exc}")
                    continue
                digest = file_md5(jpeg)
                if digest in hash_to_name:
                    existing_name = hash_to_name[digest]
                    already_recorded = any(
                        r.get("file") == existing_name and not r.get("duplicate")
                        for r in manifest
                    )
                    manifest.append(
                        {
                            "source_zip": zip_path.name,
                            "source_name": raw_name,
                            "file": existing_name,
                            "md5": digest,
                            "bytes": len(jpeg),
                            "duplicate": already_recorded,
                        }
                    )
                    kind = "już jest" if not already_recorded else "duplikat treści"
                    print(f"  {kind}: {raw_name} = {existing_name}")
                    continue
                slug = slugify(raw_name)
                dest_name = unique_name(dest, slug, used)
                (dest / dest_name).write_bytes(jpeg)
                hash_to_name[digest] = dest_name
                rec = {
                    "source_zip": zip_path.name,
                    "source_name": raw_name,
                    "file": dest_name,
                    "md5": digest,
                    "bytes": len(jpeg),
                    "duplicate": False,
                }
                manifest.append(rec)
                print(f"  {raw_name} -> {dest_name} ({len(jpeg)} B)")

    # manifest tylko unikalnych + informacja o duplikatach
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    unique_files = sorted({r["file"] for r in manifest if r.get("file")})
    print(f"Gotowe. Unikalnych zdjęć: {len(unique_files)}. Manifest: {manifest_path}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("zips", nargs="+", type=Path)
    parser.add_argument("--dest", type=Path, default=root / "images")
    parser.add_argument("--manifest", type=Path, default=root / "image-manifest.json")
    args = parser.parse_args()
    for z in args.zips:
        if not z.exists():
            print(f"Brak pliku: {z}", file=sys.stderr)
            return 1
    extract_zips(args.zips, args.dest, args.manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
