from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class Store:
    """Base of every repository class: one per aggregate, bound to the caller's session.

    (Named Store rather than Repository, which in this codebase is a code repository.)
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
