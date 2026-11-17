"""Safe extraction of uploaded repository archives (.zip, .tar.gz, .tgz, .tar).

Uploads are untrusted. Extraction refuses absolute paths and `..` segments, skips links and
device files, never trusts the sizes an archive declares (bytes are counted as they are
written), and caps the number of entries, the size of each file, the total size and the
compression ratio, so an archive bomb stops early instead of filling the disk.
"""

from __future__ import annotations

import shutil
import stat
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO, Literal

from codeagent.core.errors import (
    PayloadTooLargeError,
    UnprocessableError,
    UnsupportedMediaTypeError,
)

ArchiveFormat = Literal["zip", "tar.gz", "tar"]
_COPY_CHUNK = 1024 * 1024
_JUNK = frozenset({"__MACOSX", ".DS_Store"})


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    max_entries: int = 50_000
    max_total_bytes: int = 500 * 1024 * 1024
    max_file_bytes: int = 100 * 1024 * 1024
    max_ratio: int = 200


@dataclass(frozen=True, slots=True)
class ExtractStats:
    files: int
    bytes: int
    stripped_prefix: str | None


def detect_format(filename: str, head: bytes) -> ArchiveFormat:
    """The archive format from its magic bytes; the file name only breaks ties."""
    name = filename.lower()
    if head.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        return "zip"
    if head.startswith(b"\x1f\x8b"):
        return "tar.gz"
    if len(head) > 262 and head[257:262] == b"ustar":
        return "tar"
    if name.endswith((".zip", ".tar.gz", ".tgz", ".tar")):
        raise UnprocessableError("The archive is damaged or empty.", code="invalid_archive")
    raise UnsupportedMediaTypeError("Upload a .zip, .tar.gz or .tar archive of the repository.")


def suffix_for(fmt: ArchiveFormat) -> str:
    return {"zip": ".zip", "tar.gz": ".tar.gz", "tar": ".tar"}[fmt]


def safe_member_path(name: str) -> PurePosixPath | None:
    """The relative path an entry may be written to, or None to skip it."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or not path.parts:
        raise UnprocessableError(
            f"The archive contains an absolute path: {name}", code="unsafe_archive"
        )
    if any(part == ".." for part in path.parts):
        raise UnprocessableError(
            f"The archive contains a path outside its root: {name}", code="unsafe_archive"
        )
    if any(part in _JUNK for part in path.parts) or ".git" in path.parts:
        return None
    return path


class _Budget:
    def __init__(self, limits: ArchiveLimits, compressed_size: int) -> None:
        self.limits = limits
        self.compressed_size = max(compressed_size, 1)
        self.entries = 0
        self.total = 0

    def entry(self) -> None:
        self.entries += 1
        if self.entries > self.limits.max_entries:
            raise PayloadTooLargeError(
                f"The archive has more than {self.limits.max_entries} files."
            )

    def write(self, source: IO[bytes], target: Path) -> int:
        written = 0
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            while chunk := source.read(_COPY_CHUNK):
                written += len(chunk)
                self.total += len(chunk)
                if written > self.limits.max_file_bytes:
                    raise PayloadTooLargeError(f"{target.name} is larger than the per-file limit.")
                if self.total > self.limits.max_total_bytes:
                    raise PayloadTooLargeError(
                        "The extracted repository is larger than this deployment allows."
                    )
                if (
                    self.total > self.compressed_size * self.limits.max_ratio
                    and self.total > 8 * _COPY_CHUNK
                ):
                    raise PayloadTooLargeError(
                        "The archive expands far more than a source tree should."
                    )
                handle.write(chunk)
        return written


def _extract_zip(archive: Path, dest: Path, budget: _Budget) -> int:
    files = 0
    try:
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                if info.is_dir():
                    continue
                kind = stat.S_IFMT(info.external_attr >> 16)
                # Some writers leave the file type bits unset; only a stated non-regular type
                # (a symbolic link, a device) is skipped.
                if kind and kind != stat.S_IFREG:
                    continue
                relative = safe_member_path(info.filename)
                if relative is None:
                    continue
                budget.entry()
                with bundle.open(info) as source:
                    budget.write(source, dest / relative)
                files += 1
    except zipfile.BadZipFile as exc:
        raise UnprocessableError("The zip archive is damaged.", code="invalid_archive") from exc
    return files


def _extract_tar(archive: Path, dest: Path, budget: _Budget, *, gzip: bool) -> int:
    files = 0
    try:
        with tarfile.open(archive, "r:gz" if gzip else "r:") as bundle:
            for member in bundle:
                if not member.isfile():
                    continue  # directories are implied; links and devices are never extracted
                relative = safe_member_path(member.name)
                if relative is None:
                    continue
                budget.entry()
                source = bundle.extractfile(member)
                if source is None:
                    continue
                with source:
                    budget.write(source, dest / relative)
                files += 1
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise UnprocessableError("The tar archive is damaged.", code="invalid_archive") from exc
    return files


def strip_single_root(dest: Path) -> str | None:
    """GitHub-style archives wrap everything in one folder (`repo-main/`); unwrap it."""
    entries = [entry for entry in dest.iterdir() if entry.name not in _JUNK]
    if len(entries) != 1 or not entries[0].is_dir():
        return None
    root = entries[0]
    for child in list(root.iterdir()):
        shutil.move(str(child), dest / child.name)
    root.rmdir()
    return root.name


def extract(archive: Path, dest: Path, fmt: ArchiveFormat, limits: ArchiveLimits) -> ExtractStats:
    dest.mkdir(parents=True, exist_ok=True)
    budget = _Budget(limits, archive.stat().st_size)
    if fmt == "zip":
        files = _extract_zip(archive, dest, budget)
    else:
        files = _extract_tar(archive, dest, budget, gzip=fmt == "tar.gz")
    if files == 0:
        raise UnprocessableError("The archive contains no files.", code="empty_archive")
    return ExtractStats(files=files, bytes=budget.total, stripped_prefix=strip_single_root(dest))
