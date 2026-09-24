from pathlib import Path

from carrierbundlelab.carrier.manifest import build_manifest, compare_manifests


def test_manifest_detects_modified_file_and_symlink(tmp_path: Path):
    (tmp_path / "tree").mkdir()
    (tmp_path / "tree" / "a.txt").write_text("one")
    (tmp_path / "tree" / "link").symlink_to("a.txt")
    before = build_manifest(tmp_path / "tree")

    (tmp_path / "tree" / "a.txt").write_text("two")
    (tmp_path / "tree" / "link").unlink()
    (tmp_path / "tree" / "link").symlink_to("missing.txt")
    after = build_manifest(tmp_path / "tree")

    diff = compare_manifests(before, after)
    assert "a.txt" in diff.modified
    assert "link" in diff.symlink_target_changed
