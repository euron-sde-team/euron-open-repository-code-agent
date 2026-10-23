"""Every model, imported here so `Base.metadata` is complete for Alembic and the tests."""

from codeagent.models.api_key import ApiKey
from codeagent.models.audit import AuditEvent
from codeagent.models.conversation import Conversation, Message
from codeagent.models.index import CodeChunk, RepoFile, Symbol, SymbolRef
from codeagent.models.repository import Repository, Snapshot
from codeagent.models.task import Patch, PatchFile, ReviewComment, Task
from codeagent.models.test_run import TestRun
from codeagent.models.usage import UsageEvent
from codeagent.models.user import User
from codeagent.models.workspace import Membership, Workspace

__all__ = [
    "ApiKey",
    "AuditEvent",
    "CodeChunk",
    "Conversation",
    "Membership",
    "Message",
    "Patch",
    "PatchFile",
    "RepoFile",
    "Repository",
    "ReviewComment",
    "Snapshot",
    "Symbol",
    "SymbolRef",
    "Task",
    "TestRun",
    "UsageEvent",
    "User",
    "Workspace",
]
