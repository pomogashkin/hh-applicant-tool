from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Optional

from hh_applicant_tool.api import ApiClient


@dataclass
class AsyncHH:
    client: ApiClient
    _executor: Optional[ThreadPoolExecutor] = None

    def _ensure_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="hh-client")
        return self._executor

    async def get(self, endpoint: str, **params: Any) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._ensure_executor(), lambda: self.client.get(endpoint, **params))

    async def post(self, endpoint: str, params: dict | None = None, **kw: Any) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._ensure_executor(), lambda: self.client.post(endpoint, params or {}, **kw))

    async def put(self, endpoint: str, **params: Any) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._ensure_executor(), lambda: self.client.put(endpoint, **params))

    async def delete(self, endpoint: str, **params: Any) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._ensure_executor(), lambda: self.client.delete(endpoint, **params))

    async def get_me(self) -> dict:
        return await self.get("/me")

    async def get_similar_vacancies(self, resume_id: str, *, salary_from: int | None = None, professional_roles: list[int] | None = None, order_by: str = "publication_time") -> dict:
        params: dict[str, Any] = {"order_by": order_by}
        if salary_from:
            params["salary_from"] = salary_from
        if professional_roles:
            params["professional_role"] = professional_roles
        return await self.get(f"/resumes/{resume_id}/similar_vacancies", **params)

    async def apply(self, vacancy_id: int, resume_id: str, message: str | None = None) -> dict:
        payload: dict[str, Any] = {"vacancy_id": vacancy_id, "resume_id": resume_id}
        if message:
            payload["message"] = message
        return await self.post("/negotiations", payload)