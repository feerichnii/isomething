"""Safe IPCC extraction."""

from __future__ import annotations

import os
import stat
import zipfile
from pathlib import Path

from carrierbundlelab.errors import BundleCompatibilityError


def safe_extract_ipcc(ipcc_path: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    with zipfile.ZipFile(ipcc_path) as archive:
        for info in archive.infolist():
            _reject_unsafe_member(info)
            destination = (root / info.filename).resolve()
            if destination != root and root not in destination.parents:
                raise BundleCompatibilityError(f"IPCC entry escapes target directory: {info.filename}")
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, destination.open("wb") as handle:
                handle.write(source.read())


def _reject_unsafe_member(info: zipfile.ZipInfo) -> None:
    name = info.filename
    path = Path(name)
    if name.startswith("/") or name.startswith("\\") or path.is_absolute():
        raise BundleCompatibilityError(f"Absolute IPCC path rejected: {name}")
    if ".." in path.parts:
        raise BundleCompatibilityError(f"Path traversal rejected: {name}")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise BundleCompatibilityError(f"Symlink IPCC entry rejected: {name}")
    if os.sep == "\\" and "\\" in name:
        raise BundleCompatibilityError(f"Unsafe IPCC path rejected: {name}")
