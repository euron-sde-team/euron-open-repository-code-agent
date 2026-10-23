"""The code index of one snapshot: files, symbols, references and embedded chunks."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import BigInteger, Computed, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from codeagent.db.base import Base, IdMixin
from codeagent.db.types import Embedding


class RepoFile(IdMixin, Base):
    __tablename__ = "repo_files"

    # Denormalised from the snapshot, so every query filters on one column of one table.
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(String(1000))
    language: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    line_count: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    is_test: Mapped[bool] = mapped_column(default=False)
    symbol_count: Mapped[int] = mapped_column(default=0)
    # Null for files that are tracked but not indexed (binary or too large).
    content: Mapped[str | None] = mapped_column(Text)
    parse_error: Mapped[str | None] = mapped_column(Text)


class Symbol(IdMixin, Base):
    __tablename__ = "symbols"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"))
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repo_files.id", ondelete="CASCADE"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(300))
    qualified_name: Mapped[str] = mapped_column(String(1000))
    kind: Mapped[str] = mapped_column(String(16))
    start_line: Mapped[int]
    end_line: Mapped[int]
    signature: Mapped[str] = mapped_column(Text, default="")
    doc: Mapped[str] = mapped_column(Text, default="")
    exported: Mapped[bool] = mapped_column(default=True)
    ref_count: Mapped[int] = mapped_column(default=0)


class SymbolRef(IdMixin, Base):
    """An edge of the reference graph: a call, import or inheritance at one line."""

    __tablename__ = "symbol_refs"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"))
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repo_files.id", ondelete="CASCADE"))
    source_symbol_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE")
    )
    target_symbol_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE")
    )
    target_name: Mapped[str] = mapped_column(String(300))
    qualifier: Mapped[str | None] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(16))
    line: Mapped[int]


class CodeChunk(IdMixin, Base):
    """A retrievable range of lines with both search representations."""

    __tablename__ = "code_chunks"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"))
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repo_files.id", ondelete="CASCADE"))
    symbol_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE")
    )
    start_line: Mapped[int]
    end_line: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    # Identifier-split, stemmed words (codeintel.terms), the source of the full-text column.
    terms: Mapped[str] = mapped_column(Text, default="")
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', terms)", persisted=True)
    )
    token_count: Mapped[int] = mapped_column(default=0)
    embedding: Mapped[Any] = mapped_column(Embedding())
