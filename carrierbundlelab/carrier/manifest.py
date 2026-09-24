"""Carrier tree manifest creation and comparison."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from carrierbundlelab.models import FileManifestEntry, ManifestDiff, TreeManifest


def build_manifest(root: Path) -> TreeManifest:
    root = Path(root)
    files: dict[str, FileManifestEntry] = {}
    directories: dict[str, FileManifestEntry] = {}
    symlinks: dict[str, FileManifestEntry] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        stat = path.lstat()
        mode = stat.st_mode & 0o7777
        if path.is_symlink():
            symlinks[rel] = FileManifestEntry(
                type="symlink",
                mode=mode,
                target=os.readlink(path),
            )
        elif path.is_dir():
            directories[rel] = FileManifestEntry(type="directory", mode=mode)
        elif path.is_file():
            files[rel] = FileManifestEntry(
                type="file",
                size=stat.st_size,
                sha256=_sha256(path),
                mode=mode,
            )
    return TreeManifest(files=files, directories=directories, symlinks=symlinks)


def compare_manifests(before: TreeManifest, after: TreeManifest) -> ManifestDiff:
    before_entries = _flatten(before)
    after_entries = _flatten(after)
    before_keys = set(before_entries)
    after_keys = set(after_entries)
    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    modified: list[str] = []
    symlink_target_changed: list[str] = []
    for key in sorted(before_keys & after_keys):
        left = before_entries[key]
        right = after_entries[key]
        if left.type == "symlink" or right.type == "symlink":
            if left.target != right.target:
                symlink_target_changed.append(key)
            elif left != right:
                modified.append(key)
        elif left != right:
            modified.append(key)
    return ManifestDiff(
        added=added,
        removed=removed,
        modified=modified,
        symlink_target_changed=symlink_target_changed,
    )


def write_manifest(manifest: TreeManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_manifest_to_dict(manifest), indent=2, sort_keys=True), encoding="utf-8")


def read_manifest(path: Path) -> TreeManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return TreeManifest(
        files={k: FileManifestEntry(**v) for k, v in data.get("files", {}).items()},
        directories={k: FileManifestEntry(**v) for k, v in data.get("directories", {}).items()},
        symlinks={k: FileManifestEntry(**v) for k, v in data.get("symlinks", {}).items()},
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _flatten(manifest: TreeManifest) -> dict[str, FileManifestEntry]:
    out: dict[str, FileManifestEntry] = {}
    out.update(manifest.directories)
    out.update(manifest.files)
    out.update(manifest.symlinks)
    return out


def _manifest_to_dict(manifest: TreeManifest) -> dict[str, dict[str, dict]]:
    return {
        "files": {k: asdict(v) for k, v in manifest.files.items()},
        "directories": {k: asdict(v) for k, v in manifest.directories.items()},
        "symlinks": {k: asdict(v) for k, v in manifest.symlinks.items()},
    }
