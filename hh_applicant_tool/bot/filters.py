from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class VacancyFilters:
    professional_roles: list[int]
    salary_from: int
    remote: bool
    flexible: bool
    exclude_text: str

    @classmethod
    def from_pref_row(cls, pref: Any) -> "VacancyFilters":
        roles = [int(x) for x in (pref.professional_roles or "").split(",") if x]
        return cls(
            professional_roles=roles or [4, 6, 8, 9, 34],
            salary_from=pref.salary_from or 100000,
            remote=bool(pref.remote),
            flexible=bool(pref.flexible),
            exclude_text=pref.exclude_text or "ux ui",
        )


def vacancy_to_text(v: dict) -> str:
    name = v.get("name", "")
    employer = (v.get("employer") or {}).get("name", "")
    salary = v.get("salary") or {}
    if salary:
        s_text = f"{salary.get('from') or ''}-{salary.get('to') or ''} {salary.get('currency') or ''}".strip(" -")
    else:
        s_text = "не указана"
    schedule = (v.get("schedule") or {}).get("name") or ""
    employment = (v.get("employment") or {}).get("name") or ""
    area = (v.get("area") or {}).get("name") or ""
    url = v.get("alternate_url") or v.get("apply_alternate_url") or v.get("url") or ""

    lines = [
        f"💼 {name}",
        f"🏢 {employer}",
        f"📍 {area}",
        f"💵 Зарплата: {s_text}",
        f"🕒 График: {schedule} ({employment})",
        f"🔗 {url}",
    ]

    snippet = v.get("snippet") or {}
    for k in ("responsibility", "requirement"):
        val = snippet.get(k)
        if val:
            lines.append("")
            lines.append(val)
    return "\n".join(filter(None, lines))