"""Initial schema: accounts, workspaces, repositories, the code index, answers, tasks,
patches, reviews and test runs.

Revision ID: 0001
Revises:
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from codeagent.core.config import get_settings
from codeagent.db.types import Embedding

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)
EMPTY_LIST = sa.text("'[]'::jsonb")
EMPTY_OBJECT = sa.text("'{}'::jsonb")


def _id() -> sa.Column[object]:
    return sa.Column("id", UUID, nullable=False)


def _created() -> sa.Column[object]:
    return sa.Column("created_at", TS, nullable=False, server_default=sa.func.now())


def _updated() -> sa.Column[object]:
    return sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now())


def _fk(column: str, table: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([column], [f"{table}.id"], ondelete=ondelete)


def _int(name: str) -> sa.Column[object]:
    return sa.Column(name, sa.Integer(), nullable=False, server_default="0")


def upgrade() -> None:
    # The embedding width is fixed per deployment (EMBEDDING_DIM, 384 by default). Changing
    # it later means a new migration and `codeagent reindex`.
    dim = get_settings().embedding_dim
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "users",
        _id(),
        sa.Column("email", pg.CITEXT(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
        _int("failed_logins"),
        sa.Column("locked_until", TS),
        sa.Column("last_login_at", TS),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "workspaces",
        _id(),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("settings", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        _int("task_counter"),
        _int("run_counter"),
        sa.Column("created_by", UUID),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        _fk("created_by", "users", "SET NULL"),
    )

    op.create_table(
        "memberships",
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        _created(),
        sa.PrimaryKeyConstraint("workspace_id", "user_id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("user_id", "users", "CASCADE"),
        sa.CheckConstraint("role IN ('owner', 'maintainer', 'developer', 'viewer')", name="role"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    op.create_table(
        "api_keys",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("created_by", UUID),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("last_used_at", TS),
        sa.Column("expires_at", TS),
        sa.Column("revoked_at", TS),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prefix"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("created_by", "users", "SET NULL"),
        sa.CheckConstraint("role IN ('developer', 'viewer')", name="role"),
    )
    op.create_index("ix_api_keys_workspace_id", "api_keys", ["workspace_id"])

    op.create_table(
        "repositories",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("git_url", sa.String(500)),
        sa.Column("default_branch", sa.String(200)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("current_snapshot_id", UUID),
        sa.Column("mirror_key", sa.String(400)),
        sa.Column("settings", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("languages", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        _int("file_count"),
        _int("symbol_count"),
        _int("line_count"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_indexed_at", TS),
        sa.Column("created_by", UUID),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "slug"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("created_by", "users", "SET NULL"),
        sa.CheckConstraint("source IN ('git', 'archive')", name="source"),
        sa.CheckConstraint("status IN ('queued', 'indexing', 'ready', 'failed')", name="status"),
    )
    op.create_index(
        "ix_repositories_workspace_id_created_at", "repositories", ["workspace_id", "created_at"]
    )

    op.create_table(
        "snapshots",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("repository_id", UUID, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("upload_key", sa.String(400)),
        sa.Column("upload_name", sa.String(300)),
        sa.Column("commit_sha", sa.String(64)),
        sa.Column("branch", sa.String(200)),
        sa.Column("stats", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("warnings", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("error", sa.Text()),
        _int("attempts"),
        sa.Column("created_by", UUID),
        sa.Column("indexed_at", TS),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("repository_id", "repositories", "CASCADE"),
        _fk("created_by", "users", "SET NULL"),
        sa.CheckConstraint("status IN ('queued', 'indexing', 'ready', 'failed')", name="status"),
        sa.CheckConstraint("origin IN ('clone', 'sync', 'upload')", name="origin"),
    )
    op.create_index(
        "ix_snapshots_repository_id_created_at", "snapshots", ["repository_id", "created_at"]
    )
    # Small partial index for the stale-job reaper: only unfinished snapshots are in it.
    op.create_index(
        "ix_snapshots_unfinished",
        "snapshots",
        ["updated_at"],
        postgresql_where=sa.text("status IN ('queued', 'indexing')"),
    )
    op.create_foreign_key(
        "fk_repositories_current_snapshot_id_snapshots",
        "repositories",
        "snapshots",
        ["current_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "repo_files",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("snapshot_id", UUID, nullable=False),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("language", sa.String(40), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false()),
        _int("symbol_count"),
        sa.Column("content", sa.Text()),
        sa.Column("parse_error", sa.Text()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_id", "path"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("snapshot_id", "snapshots", "CASCADE"),
    )
    # Full-text code search narrows candidate files with trigrams before splitting lines.
    op.create_index(
        "ix_repo_files_content_trgm",
        "repo_files",
        ["content"],
        postgresql_using="gin",
        postgresql_ops={"content": "gin_trgm_ops"},
    )

    op.create_table(
        "symbols",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("snapshot_id", UUID, nullable=False),
        sa.Column("file_id", UUID, nullable=False),
        sa.Column("parent_id", UUID),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("qualified_name", sa.String(1000), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False, server_default=""),
        sa.Column("doc", sa.Text(), nullable=False, server_default=""),
        sa.Column("exported", sa.Boolean(), nullable=False, server_default=sa.true()),
        _int("ref_count"),
        sa.PrimaryKeyConstraint("id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("snapshot_id", "snapshots", "CASCADE"),
        _fk("file_id", "repo_files", "CASCADE"),
        _fk("parent_id", "symbols", "CASCADE"),
        sa.CheckConstraint(
            "kind IN ('class', 'function', 'method', 'constant', 'interface', 'type', 'enum', "
            "'struct')",
            name="kind",
        ),
    )
    op.create_index("ix_symbols_snapshot_id_name", "symbols", ["snapshot_id", "name"])
    op.create_index("ix_symbols_file_id_start_line", "symbols", ["file_id", "start_line"])
    op.execute("CREATE INDEX ix_symbols_name_trgm ON symbols USING gin (lower(name) gin_trgm_ops)")

    op.create_table(
        "symbol_refs",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("snapshot_id", UUID, nullable=False),
        sa.Column("file_id", UUID, nullable=False),
        sa.Column("source_symbol_id", UUID),
        sa.Column("target_symbol_id", UUID),
        sa.Column("target_name", sa.String(300), nullable=False),
        sa.Column("qualifier", sa.String(300)),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("snapshot_id", "snapshots", "CASCADE"),
        _fk("file_id", "repo_files", "CASCADE"),
        _fk("source_symbol_id", "symbols", "CASCADE"),
        _fk("target_symbol_id", "symbols", "CASCADE"),
        sa.CheckConstraint("kind IN ('call', 'import', 'inherit')", name="kind"),
    )
    # Callers of a symbol, and what a symbol calls: the two directions of the graph.
    op.create_index("ix_symbol_refs_target_symbol_id", "symbol_refs", ["target_symbol_id"])
    op.create_index("ix_symbol_refs_source_symbol_id", "symbol_refs", ["source_symbol_id"])
    op.create_index("ix_symbol_refs_file_id", "symbol_refs", ["file_id"])

    op.create_table(
        "code_chunks",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("snapshot_id", UUID, nullable=False),
        sa.Column("file_id", UUID, nullable=False),
        sa.Column("symbol_id", UUID),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("terms", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "tsv",
            pg.TSVECTOR(),
            sa.Computed("to_tsvector('simple', terms)", persisted=True),
        ),
        _int("token_count"),
        sa.Column("embedding", Embedding(dim), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("snapshot_id", "snapshots", "CASCADE"),
        _fk("file_id", "repo_files", "CASCADE"),
        _fk("symbol_id", "symbols", "CASCADE"),
    )
    op.create_index("ix_code_chunks_snapshot_id", "code_chunks", ["snapshot_id"])
    op.create_index("ix_code_chunks_file_id", "code_chunks", ["file_id"])
    op.create_index("ix_code_chunks_tsv", "code_chunks", ["tsv"], postgresql_using="gin")
    op.create_index(
        "ix_code_chunks_embedding_hnsw",
        "code_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "conversations",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("repository_id", UUID),
        sa.Column("title", sa.String(200), nullable=False),
        _int("message_count"),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("user_id", "users", "CASCADE"),
        _fk("repository_id", "repositories", "SET NULL"),
    )
    op.create_index(
        "ix_conversations_workspace_id_user_id_updated_at",
        "conversations",
        ["workspace_id", "user_id", "updated_at"],
    )

    op.create_table(
        "messages",
        _id(),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("sources", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("usage", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        _fk("conversation_id", "conversations", "CASCADE"),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="role"),
    )
    op.create_index(
        "ix_messages_conversation_id_created_at", "messages", ["conversation_id", "created_at"]
    )

    op.create_table(
        "tasks",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("repository_id", UUID, nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("skill", sa.String(32)),
        sa.Column("planner", sa.String(120)),
        sa.Column("base_snapshot_id", UUID),
        sa.Column("base_commit", sa.String(64)),
        sa.Column("error_code", sa.String(40)),
        sa.Column("error", sa.Text()),
        sa.Column("trace", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("usage", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        _int("attempts"),
        _int("patch_count"),
        sa.Column("created_by", UUID),
        sa.Column("started_at", TS),
        sa.Column("finished_at", TS),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "number"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("repository_id", "repositories", "CASCADE"),
        _fk("base_snapshot_id", "snapshots", "SET NULL"),
        _fk("created_by", "users", "SET NULL"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'awaiting_review', 'approved', 'applying', "
            "'applied', 'rejected', 'failed', 'cancelled')",
            name="status",
        ),
    )
    op.create_index("ix_tasks_workspace_id_updated_at", "tasks", ["workspace_id", "updated_at"])
    op.create_index("ix_tasks_repository_id_created_at", "tasks", ["repository_id", "created_at"])
    op.create_index(
        "ix_tasks_unfinished",
        "tasks",
        ["updated_at"],
        postgresql_where=sa.text("status IN ('queued', 'running', 'applying')"),
    )

    op.create_table(
        "test_runs",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("repository_id", UUID, nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", UUID),
        sa.Column("task_id", UUID),
        sa.Column("patch_id", UUID),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("commit_sha", sa.String(64)),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("backend", sa.String(16)),
        sa.Column("image", sa.String(200)),
        sa.Column("limits", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("duration_ms", sa.Integer()),
        _int("total"),
        _int("passed"),
        _int("failed"),
        _int("errors"),
        _int("skipped"),
        sa.Column("results", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("log_tail", sa.Text(), nullable=False, server_default=""),
        sa.Column("log_key", sa.String(400)),
        sa.Column("log_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text()),
        _int("attempts"),
        sa.Column("created_by", UUID),
        sa.Column("started_at", TS),
        sa.Column("finished_at", TS),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "number"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("repository_id", "repositories", "CASCADE"),
        _fk("snapshot_id", "snapshots", "SET NULL"),
        _fk("task_id", "tasks", "SET NULL"),
        _fk("created_by", "users", "SET NULL"),
        sa.CheckConstraint(
            "trigger IN ('manual', 'agent_baseline', 'agent_verify', 'patch')", name="trigger"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'passed', 'failed', 'error', 'timed_out', "
            "'cancelled')",
            name="status",
        ),
    )
    op.create_index(
        "ix_test_runs_workspace_id_created_at", "test_runs", ["workspace_id", "created_at"]
    )
    op.create_index(
        "ix_test_runs_repository_id_created_at", "test_runs", ["repository_id", "created_at"]
    )
    op.create_index("ix_test_runs_task_id", "test_runs", ["task_id"])
    op.create_index(
        "ix_test_runs_unfinished",
        "test_runs",
        ["updated_at"],
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    op.create_table(
        "patches",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("task_id", UUID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("summary", sa.String(300), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("plan", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("diff", sa.Text(), nullable=False),
        sa.Column("files", pg.JSONB(), nullable=False, server_default=EMPTY_LIST),
        _int("additions"),
        _int("deletions"),
        sa.Column("base_commit", sa.String(64)),
        sa.Column("planner", sa.String(120), nullable=False),
        sa.Column("skill", sa.String(32), nullable=False),
        sa.Column("baseline_run_id", UUID),
        sa.Column("verify_run_id", UUID),
        sa.Column("decided_by", UUID),
        sa.Column("decided_at", TS),
        sa.Column("decision_note", sa.Text()),
        sa.Column("applied_branch", sa.String(200)),
        sa.Column("applied_commit", sa.String(64)),
        sa.Column("applied_by", UUID),
        sa.Column("applied_at", TS),
        sa.Column("apply_error", sa.Text()),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "revision"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("task_id", "tasks", "CASCADE"),
        _fk("baseline_run_id", "test_runs", "SET NULL"),
        _fk("verify_run_id", "test_runs", "SET NULL"),
        _fk("decided_by", "users", "SET NULL"),
        _fk("applied_by", "users", "SET NULL"),
        sa.CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected', 'superseded', 'applying', 'applied')",
            name="status",
        ),
    )
    op.create_index("ix_patches_workspace_id_status", "patches", ["workspace_id", "status"])
    op.create_foreign_key(
        "fk_test_runs_patch_id_patches",
        "test_runs",
        "patches",
        ["patch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_test_runs_patch_id", "test_runs", ["patch_id"])

    op.create_table(
        "patch_files",
        _id(),
        sa.Column("patch_id", UUID, nullable=False),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("change_type", sa.String(16), nullable=False),
        _int("additions"),
        _int("deletions"),
        sa.Column("language", sa.String(40), nullable=False, server_default="Text"),
        sa.Column("old_content", sa.Text()),
        sa.Column("new_content", sa.Text()),
        sa.PrimaryKeyConstraint("id"),
        _fk("patch_id", "patches", "CASCADE"),
        sa.CheckConstraint("change_type IN ('added', 'modified', 'deleted')", name="change_type"),
    )
    op.create_index("ix_patch_files_patch_id", "patch_files", ["patch_id"])

    op.create_table(
        "review_comments",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("patch_id", UUID, nullable=False),
        sa.Column("author_id", UUID),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("path", sa.String(1000)),
        sa.Column("line", sa.Integer()),
        sa.Column("side", sa.String(8)),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("patch_id", "patches", "CASCADE"),
        _fk("author_id", "users", "SET NULL"),
        sa.CheckConstraint("side IS NULL OR side IN ('old', 'new')", name="side"),
    )
    op.create_index(
        "ix_review_comments_patch_id_created_at", "review_comments", ["patch_id", "created_at"]
    )

    op.create_table(
        "usage_events",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("user_id", UUID),
        sa.Column("api_key_id", UUID),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("engine", sa.String(120), nullable=False),
        _int("latency_ms"),
        _int("prompt_tokens"),
        _int("completion_tokens"),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("user_id", "users", "SET NULL"),
        _fk("api_key_id", "api_keys", "SET NULL"),
        sa.CheckConstraint("kind IN ('ask', 'search')", name="kind"),
    )
    op.create_index(
        "ix_usage_events_workspace_id_created_at", "usage_events", ["workspace_id", "created_at"]
    )

    op.create_table(
        "audit_events",
        _id(),
        sa.Column("workspace_id", UUID),
        sa.Column("actor_user_id", UUID),
        sa.Column("actor_api_key_id", UUID),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64)),
        sa.Column("details", pg.JSONB(), nullable=False, server_default=EMPTY_OBJECT),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("actor_user_id", "users", "SET NULL"),
        _fk("actor_api_key_id", "api_keys", "SET NULL"),
    )
    op.create_index(
        "ix_audit_events_workspace_id_created_at", "audit_events", ["workspace_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_test_runs_patch_id_patches", "test_runs", type_="foreignkey")
    op.drop_constraint(
        "fk_repositories_current_snapshot_id_snapshots", "repositories", type_="foreignkey"
    )
    for table in (
        "audit_events",
        "usage_events",
        "review_comments",
        "patch_files",
        "patches",
        "test_runs",
        "tasks",
        "messages",
        "conversations",
        "code_chunks",
        "symbol_refs",
        "symbols",
        "repo_files",
        "snapshots",
        "repositories",
        "api_keys",
        "memberships",
        "workspaces",
        "users",
    ):
        op.drop_table(table)
