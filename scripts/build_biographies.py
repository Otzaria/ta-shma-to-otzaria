"""Fetch all rabanan biographies from the Tashma API and build an obfuscated
release file (biographies.tsb) plus a plain-data hash (biographies.sha256).

Environment:
  TASHMA_API_KEY  - Tashma API key (scope rabanan:read)
  OBF_KEY         - shared obfuscation key (same value lives in the Otzaria repo)

Output (in ./out):
  biographies.tsb     - "TSB1" magic + XOR(gzip(canonical JSON), keystream)
  biographies.sha256  - hex SHA-256 of the canonical JSON (used for change detection)

TSB1 format, for the reader side:
  bytes 0..3   ASCII "TSB1"
  bytes 4..    gzip(canonical_json_utf8) XORed byte-by-byte with
               SHA256(OBF_KEY_utf8) repeated cyclically (32-byte keystream)
"""

import gzip
import hashlib
import json
import os
import sys
import time

import requests

BASE = "https://api.tashma.co.il"

session = requests.Session()
session.headers["x-api-key"] = os.environ["TASHMA_API_KEY"]


def get(path):
    last_err = None
    for attempt in range(4):
        try:
            r = session.get(BASE + path, timeout=120)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except requests.RequestException as e:
            last_err = str(e)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET {path} failed after retries: {last_err}")


def translation_text(entry):
    """Best-effort extraction of display text from a translation entry."""
    if not isinstance(entry, dict):
        return None
    for key in ("he", "name", "title", "text", "value", "label"):
        v = entry.get(key)
        if isinstance(v, dict):
            v = v.get("he") or next((x for x in v.values() if isinstance(x, str)), None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def main():
    print("Fetching rabanan list...")
    listing = get("/api/rabanan/")
    rav_ids = sorted(r["_id"] for r in listing["data"])
    print(f"  {len(rav_ids)} entries")

    translation_raw = listing.get("translation") or []
    translation_map = {}
    for t in translation_raw:
        if isinstance(t, dict) and "_id" in t:
            translation_map[str(t["_id"])] = t

    print("Fetching calendar dates...")
    calendar = get("/api/rabanan/calendar-dates") or {"data": []}
    calendar_by_id = {c["_id"]: c for c in calendar["data"]}

    print("Fetching full entries...")
    entries = []
    for i, rav_id in enumerate(rav_ids):
        doc = get(f"/api/rabanan/{rav_id}")
        if doc is None:
            print(f"  WARN: id {rav_id} returned 404, skipping")
            continue
        data = doc.get("data") or {}
        # The per-entry response repeats the translation collection; drop it.
        data.pop("translation", None)

        cal = calendar_by_id.get(rav_id, {})
        entry = {
            "id": rav_id,
            "name": cal.get("name"),  # pre-composed display name when available
            "slug": cal.get("slug"),
            "birthHebrew": cal.get("birthHebrew"),
            "deathHebrew": cal.get("deathHebrew"),
            "doc": data,
        }
        # Resolve ObjectId references against the translation collection.
        resolved = {}
        for field in ("titlePre", "titlePost", "generation"):
            ref = data.get(field)
            if isinstance(ref, str) and ref in translation_map:
                text = translation_text(translation_map[ref])
                if text:
                    resolved[field] = text
        for field in ("communities", "countries"):
            refs = data.get(field)
            if isinstance(refs, list):
                texts = [
                    translation_text(translation_map[r])
                    for r in refs
                    if isinstance(r, str) and r in translation_map
                ]
                texts = [t for t in texts if t]
                if texts:
                    resolved[field] = texts
        if resolved:
            entry["resolved"] = resolved
        entries.append(entry)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(rav_ids)}")

    payload = {
        "format": "tashma-biographies",
        "version": 1,
        "entries": entries,
        "translation": translation_raw,
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()

    keystream = hashlib.sha256(os.environ["OBF_KEY"].encode("utf-8")).digest()
    compressed = gzip.compress(canonical, mtime=0)
    obfuscated = bytes(b ^ keystream[i % len(keystream)] for i, b in enumerate(compressed))

    os.makedirs("out", exist_ok=True)
    with open("out/biographies.tsb", "wb") as f:
        f.write(b"TSB1" + obfuscated)
    with open("out/biographies.sha256", "w") as f:
        f.write(digest + "\n")

    print(f"Entries: {len(entries)}")
    print(f"Plain size: {len(canonical):,} bytes, file size: {len(obfuscated) + 4:,} bytes")
    print(f"Data hash: {digest}")


if __name__ == "__main__":
    sys.exit(main())
