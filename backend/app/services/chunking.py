from __future__ import annotations

from collections.abc import Iterable


def chunk_symbols(symbols: Iterable[str], size: int) -> list[list[str]]:
    n = int(size or 0)
    if n <= 0:
        raise ValueError("chunk size must be > 0")
    uniq: list[str] = []
    seen: set[str] = set()
    for raw in symbols or []:
        s = (raw or "").strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    return [uniq[i : i + n] for i in range(0, len(uniq), n)]

