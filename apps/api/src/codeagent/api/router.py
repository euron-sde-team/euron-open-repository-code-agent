from __future__ import annotations

from fastapi import APIRouter

from codeagent.api.routes import (
    auth,
    chat,
    health,
    repositories,
    review,
    search,
    tasks,
    test_runs,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(health.router)

v1 = APIRouter(prefix="/api/v1")
for module in (
    auth,
    workspaces,
    repositories,
    search,
    chat,
    tasks,
    review,
    test_runs,
):
    v1.include_router(module.router)
v1.include_router(health.v1)
api_router.include_router(v1)
