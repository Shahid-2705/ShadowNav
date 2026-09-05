"""Fetch IO-VNBD S-side sequences.

The repository stores every CSV in Git LFS, so ``raw.githubusercontent.com``
returns a ~130-byte pointer stub rather than the file. The working path is
``media.githubusercontent.com/media/...``. Confirmed by fetching
``S-Vta10.csv`` on 2026-09-05: stub 131 bytes via raw, 296597 bytes via media.

The dataset folder name is misspelled upstream -- ``Synchronised V abd S
datasets`` -- which is why the path constant below looks like a typo. It is not.

IO-VNBD is CC BY 4.0 via its Data in Brief version (PMC7907232). We fetch, we do
not redistribute: ``data/`` is gitignored. Attribution belongs in any writeup:
Onyekpe, Palade, Kanarachos, Szkolnik (Coventry University), arXiv:2005.01701.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "onyekpeu/IO-VNBD"
BRANCH = "master"

# Upstream misspelling preserved deliberately. Do not "fix" it.
SYNC_DIR = "Synchronised V abd S datasets"
S_DIR = f"{SYNC_DIR}/Uncategorised IOVNB Dataset/S-Dataset"
V_DIR = f"{SYNC_DIR}/Uncategorised IOVNB Dataset/V-Dataset"

MEDIA_ROOT = f"https://media.githubusercontent.com/media/{REPO}/{BRANCH}"
API_ROOT = f"https://api.github.com/repos/{REPO}/contents"

LFS_STUB_MAX_BYTES = 512
_LFS_MAGIC = b"version https://git-lfs"


class FetchError(RuntimeError):
    pass


def default_data_dir() -> Path:
    """``<repo>/data`` -- gitignored, resolved relative to this file."""
    return Path(__file__).resolve().parents[3] / "data"


def _url(remote_path: str) -> str:
    return f"{MEDIA_ROOT}/{urllib.parse.quote(remote_path)}"


def list_s_sequences(timeout: float = 30.0) -> list[str]:
    """Names of every S-side CSV, from the GitHub contents API."""
    api = f"{API_ROOT}/{urllib.parse.quote(S_DIR)}?ref={BRANCH}"
    try:
        with urllib.request.urlopen(api, timeout=timeout) as resp:
            entries = json.load(resp)
    except urllib.error.URLError as exc:  # pragma: no cover - network
        raise FetchError(f"could not list {S_DIR}: {exc}") from exc
    if isinstance(entries, dict):  # pragma: no cover - API error envelope
        raise FetchError(f"GitHub API error: {entries.get('message')}")
    return sorted(e["name"] for e in entries if e["name"].endswith(".csv"))


def fetch_sequence(name: str, dest_dir: Path, *, timeout: float = 120.0,
                   overwrite: bool = False) -> Path:
    """Download one S-side CSV, verifying it is not an LFS pointer stub."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    if dest.exists() and not overwrite and dest.stat().st_size > LFS_STUB_MAX_BYTES:
        return dest

    url = _url(f"{S_DIR}/{name}")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = resp.read()
    except urllib.error.URLError as exc:  # pragma: no cover - network
        raise FetchError(f"could not fetch {name}: {exc}") from exc

    if payload.startswith(_LFS_MAGIC) or len(payload) <= LFS_STUB_MAX_BYTES:
        raise FetchError(
            f"{name} came back as a {len(payload)}-byte Git LFS pointer stub. "
            f"The media.githubusercontent.com path is the one that works; "
            f"raw.githubusercontent.com will always return the stub."
        )
    dest.write_bytes(payload)
    return dest


def fetch_all(dest_dir: Path | None = None, *, names: list[str] | None = None,
              workers: int = 6, overwrite: bool = False) -> list[Path]:
    dest_dir = dest_dir or (default_data_dir() / "iovnbd" / "S")
    names = names or list_s_sequences()
    out: list[Path] = []
    errors: list[str] = []
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_sequence, n, dest_dir, overwrite=overwrite): n
            for n in names
        }
        for fut in cf.as_completed(futures):
            name = futures[fut]
            try:
                out.append(fut.result())
            except FetchError as exc:
                errors.append(f"{name}: {exc}")
    if errors:
        raise FetchError("some sequences failed:\n  " + "\n  ".join(errors))
    return sorted(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", type=Path, default=None)
    ap.add_argument("--only", nargs="*", default=None, help="specific CSV names")
    ap.add_argument("--list", action="store_true", help="list names and exit")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        for n in list_s_sequences():
            print(n)
        return 0

    dest = args.dest or (default_data_dir() / "iovnbd" / "S")
    paths = fetch_all(dest, names=args.only, overwrite=args.overwrite)
    total = sum(p.stat().st_size for p in paths)
    print(f"fetched {len(paths)} sequences -> {dest} ({total / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
