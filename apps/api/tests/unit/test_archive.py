"""Archives are untrusted input: paths, sizes and ratios are checked while extracting."""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from codeagent.codeintel.archive import (
    ArchiveLimits,
    detect_format,
    extract,
    safe_member_path,
)
from codeagent.core.errors import (
    PayloadTooLargeError,
    UnprocessableError,
    UnsupportedMediaTypeError,
)

LIMITS = ArchiveLimits(
    max_entries=50, max_total_bytes=1_000_000, max_file_bytes=100_000, max_ratio=50
)


def make_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def make_tar(path: Path, members: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def test_a_zip_is_extracted_and_its_single_root_folder_is_unwrapped(tmp_path: Path) -> None:
    archive = tmp_path / "repo.zip"
    make_zip(archive, {"repo-main/app.py": b"print(1)\n", "repo-main/lib/util.py": b"x = 1\n"})
    stats = extract(archive, tmp_path / "out", "zip", LIMITS)
    assert stats.files == 2
    assert stats.stripped_prefix == "repo-main"
    assert (tmp_path / "out" / "app.py").read_text() == "print(1)\n"
    assert (tmp_path / "out" / "lib" / "util.py").exists()


def test_a_tar_gz_is_extracted(tmp_path: Path) -> None:
    archive = tmp_path / "repo.tar.gz"
    make_tar(archive, {"a.txt": b"one", "b/c.txt": b"two"})
    stats = extract(archive, tmp_path / "out", "tar.gz", LIMITS)
    assert stats.files == 2
    assert (tmp_path / "out" / "b" / "c.txt").read_bytes() == b"two"


@pytest.mark.parametrize("name", ["../evil.py", "/etc/passwd", "a/../../evil.py", "\\\\host\\x"])
def test_unsafe_member_paths_are_refused(name: str) -> None:
    with pytest.raises(UnprocessableError):
        safe_member_path(name)


@pytest.mark.parametrize("name", ["__MACOSX/._a", ".git/config", "repo/.git/HEAD"])
def test_junk_and_git_metadata_are_skipped(name: str) -> None:
    assert safe_member_path(name) is None


def test_safe_member_paths_are_normalised() -> None:
    assert str(safe_member_path("./src//app.py")) == "src/app.py"


def test_a_zip_slip_member_is_never_written_outside(tmp_path: Path) -> None:
    archive = tmp_path / "slip.zip"
    make_zip(archive, {"../escaped.txt": b"gotcha", "ok.txt": b"fine"})
    with pytest.raises(UnprocessableError, match="outside"):
        extract(archive, tmp_path / "out", "zip", LIMITS)
    assert not (tmp_path / "escaped.txt").exists()


def test_links_are_not_extracted(tmp_path: Path) -> None:
    archive = tmp_path / "links.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tar.addfile(info)
        data = b"real"
        file_info = tarfile.TarInfo("real.txt")
        file_info.size = len(data)
        tar.addfile(file_info, io.BytesIO(data))
    out = tmp_path / "out"
    extract(archive, out, "tar.gz", LIMITS)
    assert not (out / "link").exists()
    assert (out / "real.txt").exists()


def test_a_decompression_bomb_is_stopped_by_the_ratio(tmp_path: Path) -> None:
    archive = tmp_path / "bomb.zip"
    make_zip(archive, {"zeros.txt": b"\0" * (12 * 1024 * 1024)})
    roomy = ArchiveLimits(max_total_bytes=100_000_000, max_file_bytes=100_000_000, max_ratio=50)
    with pytest.raises(PayloadTooLargeError, match="expands"):
        extract(archive, tmp_path / "out", "zip", roomy)


def test_too_many_entries_are_refused(tmp_path: Path) -> None:
    archive = tmp_path / "many.zip"
    make_zip(archive, {f"f{i}.txt": b"x" for i in range(60)})
    with pytest.raises(PayloadTooLargeError, match="more than"):
        extract(archive, tmp_path / "out", "zip", LIMITS)


def test_an_empty_archive_is_refused(tmp_path: Path) -> None:
    archive = tmp_path / "empty.zip"
    make_zip(archive, {})
    with pytest.raises(UnprocessableError):
        extract(archive, tmp_path / "out", "zip", LIMITS)


def test_format_comes_from_magic_bytes_not_the_name() -> None:
    assert detect_format("whatever.bin", b"PK\x03\x04rest") == "zip"
    assert detect_format("x", b"\x1f\x8bdata") == "tar.gz"
    with pytest.raises(UnsupportedMediaTypeError):
        detect_format("notes.txt", b"just text")
    with pytest.raises(UnprocessableError):
        detect_format("broken.zip", b"garbage")
