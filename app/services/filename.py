from __future__ import annotations

import re


def safe_filename_part(value: str | None, fallback: str = "export") -> str:
    text = re.sub(r"[\\/:*?\"<>|]+", " ", str(value or "").strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text or fallback
