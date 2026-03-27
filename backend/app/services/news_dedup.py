"""
Cross-source news dedup (minimal MVP).

Rules implemented:
1. Canonical URL: strip scheme-relative duplicates, remove common tracking query params (utm_*, fbclid, gclid, mc_cid, ref).
2. Normalized title: lowercased, collapsed whitespace, stripped of most punctuation for fingerprint.
3. Same canonical_url → same document (update sources list in raw_sources).
4. Same title_fingerprint + same calendar day (UTC) → duplicate.
5. Title similarity: difflib.SequenceMatcher ratio ≥ 0.90 and published_at within 48h → duplicate (same cluster).

Coverage counts use dedup_cluster_id (or id) so each story counts once per entity/day.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

_TRACKING_PARAMS = frozenset(
    "utm_source utm_medium utm_campaign utm_term utm_content fbclid gclid mc_cid ref _ga".split()
)


def canonicalize_url(url: str) -> str:
    if not url or not url.strip():
        return ""
    u = url.strip()
    try:
        p = urlparse(u)
        if not p.netloc:
            return u
        q = parse_qs(p.query, keep_blank_values=False)
        filtered = [(k, v) for k, v in q.items() if k.lower() not in _TRACKING_PARAMS]
        filtered.sort(key=lambda x: x[0])
        new_query = urlencode(filtered, doseq=True)
        return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/", "", new_query, ""))
    except Exception:
        return u


def normalize_title_for_fingerprint(title: str) -> str:
    t = (title or "").lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s\-]", "", t, flags=re.UNICODE)
    return t.strip()[:500]


def title_similarity(a: str, b: str) -> float:
    na = normalize_title_for_fingerprint(a)
    nb = normalize_title_for_fingerprint(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


SIMILARITY_THRESHOLD = 0.90
TIME_WINDOW_HOURS = 48


def should_merge_as_duplicate(
    url_a: str,
    title_a: str,
    pub_a: datetime | None,
    url_b: str,
    title_b: str,
    pub_b: datetime | None,
) -> bool:
    ca = canonicalize_url(url_a)
    cb = canonicalize_url(url_b)
    if ca and cb and ca == cb:
        return True
    fp_a = normalize_title_for_fingerprint(title_a)
    fp_b = normalize_title_for_fingerprint(title_b)
    if fp_a and fp_a == fp_b:
        da = pub_a.date() if pub_a else None
        db = pub_b.date() if pub_b else None
        if da and db and da == db:
            return True
    if title_similarity(title_a, title_b) >= SIMILARITY_THRESHOLD:
        if pub_a and pub_b:
            delta = abs((pub_a - pub_b).total_seconds())
            if delta <= TIME_WINDOW_HOURS * 3600:
                return True
    return False


def new_cluster_id() -> uuid.UUID:
    return uuid.uuid4()
