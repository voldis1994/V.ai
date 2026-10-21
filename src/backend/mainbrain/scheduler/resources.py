from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator


class ResourceScheduler:
    """Resursus apzinoša paralelitāte ar failu bloķēšanu."""

    def __init__(
        self,
        max_agents: int = 4,
        max_llm: int = 2,
        max_browser: int = 2,
    ) -> None:
        self.agent_sem = asyncio.Semaphore(max_agents)
        self.llm_sem = asyncio.Semaphore(max_llm)
        self.browser_sem = asyncio.Semaphore(max_browser)
        self._file_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._file_owners: dict[str, str] = {}
        self._owner_guard = threading.Lock()

    @asynccontextmanager
    async def agent_slot(self) -> AsyncIterator[None]:
        async with self.agent_sem:
            yield

    @asynccontextmanager
    async def llm_slot(self) -> AsyncIterator[None]:
        async with self.llm_sem:
            yield

    @asynccontextmanager
    async def browser_slot(self) -> AsyncIterator[None]:
        async with self.browser_sem:
            yield

    def acquire_file(self, path: str, owner: str) -> bool:
        lock = self._file_locks[path]
        if not lock.acquire(blocking=False):
            return False
        with self._owner_guard:
            self._file_owners[path] = owner
        return True

    def release_file(self, path: str, owner: str) -> None:
        with self._owner_guard:
            current = self._file_owners.get(path)
            if current != owner:
                return
            del self._file_owners[path]
        self._file_locks[path].release()

    def file_owner(self, path: str) -> str | None:
        return self._file_owners.get(path)
