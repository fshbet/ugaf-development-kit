"""Tests for the file system abstraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from ugaf.platform.filesystem import LocalFileSystemProvider


@pytest.fixture
def fs() -> LocalFileSystemProvider:
    return LocalFileSystemProvider()


def test_exists_false_for_missing_path(fs: LocalFileSystemProvider, tmp_path: Path) -> None:
    assert fs.exists(str(tmp_path / "missing.txt")) is False


def test_write_then_read_bytes(fs: LocalFileSystemProvider, tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    fs.write_bytes(str(target), b"hello world")
    assert fs.exists(str(target)) is True
    assert fs.read_bytes(str(target)) == b"hello world"


def test_write_bytes_creates_parent_dirs(fs: LocalFileSystemProvider, tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "file.txt"
    fs.write_bytes(str(target), b"data")
    assert target.exists()
    assert target.read_bytes() == b"data"


def test_list_dir_sorted(fs: LocalFileSystemProvider, tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "c.txt").write_text("c")
    assert fs.list_dir(str(tmp_path)) == ["a.txt", "b.txt", "c.txt"]


def test_make_dirs(fs: LocalFileSystemProvider, tmp_path: Path) -> None:
    target = tmp_path / "one" / "two" / "three"
    fs.make_dirs(str(target))
    assert target.is_dir()


def test_make_dirs_is_idempotent(fs: LocalFileSystemProvider, tmp_path: Path) -> None:
    target = tmp_path / "one"
    fs.make_dirs(str(target))
    fs.make_dirs(str(target))  # should not raise
    assert target.is_dir()


def test_remove_file(fs: LocalFileSystemProvider, tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("data")
    fs.remove(str(target))
    assert not target.exists()


def test_remove_directory_recursively(fs: LocalFileSystemProvider, tmp_path: Path) -> None:
    directory = tmp_path / "dir"
    (directory / "nested").mkdir(parents=True)
    (directory / "nested" / "file.txt").write_text("data")
    fs.remove(str(directory))
    assert not directory.exists()
