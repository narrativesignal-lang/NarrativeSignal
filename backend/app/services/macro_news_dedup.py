"""
Near-duplicate collapsing for macro RSS news (in-memory, list output only).

Conservative heuristics to limit false merges. Does not persist or alter ingestion.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from app.services.news_dedup import canonicalize_url

if TYPE_CHECKING:
  from app.services.macro_news import MacroNewsItem

_GOOGLE = "news.google.com"


def ensure_utc(dt: datetime) -> datetime:
    """RSS rows occasionally yield naive datetimes; mixing naive + aware breaks subtraction in Python 3."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# Identical normalized title: allow merge only within this window (recurring headlines).
_IDENTICAL_MAX_DELTA = timedelta(hours=48)
# Fuzzy title match: tighter window + higher similarity.
_FUZZY_MAX_DELTA = timedelta(hours=36)
_FUZZY_SEQUENCE_THRESHOLD = 0.91
_MIN_TOKENS_FOR_FUZZY = 5
# Max distinct *other* outlets named in API (payload cap); duplicate_count is exact cluster size.
_RELATED_PUBLISHERS_CAP = 5

# Optional trailing " | Outlet" (display titles already drop main " - Publisher" from RSS).
_TRAIL_PIPE = re.compile(r"\s*\|\s*[^|\n]{1,80}\s*$", re.UNICODE)


def _nfkc(s: str) -> str:
  return unicodedata.normalize("NFKC", s or "")


def normalize_title_for_cluster(title: str) -> str:
  """
  Aggressive normalization for duplicate detection only (not for display).
  Lowercase, strip punctuation, collapse space, trim common trailing source fragments.
  """
  t = _nfkc(title.strip().lower())
  t = _TRAIL_PIPE.sub("", t).strip()
  t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
  t = re.sub(r"\s+", " ", t).strip()
  return t[:400]


def _title_tokens(norm: str) -> list[str]:
  return [x for x in norm.split() if len(x) > 1]


def _sequence_similarity(a: str, b: str) -> float:
  if not a or not b:
    return 0.0
  return SequenceMatcher(None, a, b).ratio()


def _token_jaccard(norm_a: str, norm_b: str) -> float:
  ta = set(_title_tokens(norm_a))
  tb = set(_title_tokens(norm_b))
  if not ta or not tb:
    return 0.0
  inter = len(ta & tb)
  uni = len(ta | tb)
  return inter / uni if uni else 0.0


def _url_quality(url: str | None) -> int:
  """Higher = more likely original article. Used for keep-best tie-break."""
  if not url or not url.strip():
    return 0
  if _GOOGLE in url.lower():
    return 1
  return 2


def _related_publishers_others(members: list["MacroNewsItem"], representative: "MacroNewsItem") -> list[str]:
  """Distinct outlet names in the cluster excluding the representative's primary source, capped."""
  rep_key = (representative.source or "").strip().lower()
  seen: set[str] = set()
  out: list[str] = []
  for m in members:
    s = (m.source or "").strip()
    if not s:
      continue
    key = s.lower()
    if key == rep_key:
      continue
    if key in seen:
      continue
    seen.add(key)
    out.append(s)
  out.sort(key=str.lower)
  return out[:_RELATED_PUBLISHERS_CAP]


def _summary_score(s: str | None) -> int:
  if not s or not str(s).strip():
    return 0
  return len(str(s).strip())


def _better_representative(a: "MacroNewsItem", b: "MacroNewsItem") -> "MacroNewsItem":
  """Pick the single best item when merging a duplicate cluster."""
  imp_a = a.impact if a.impact is not None else float("-inf")
  imp_b = b.impact if b.impact is not None else float("-inf")
  if imp_a != imp_b:
    return a if imp_a > imp_b else b
  if a.publisher_tier != b.publisher_tier:
    return a if a.publisher_tier < b.publisher_tier else b
  qa, qb = _url_quality(a.url), _url_quality(b.url)
  if qa != qb:
    return a if qa > qb else b
  sa, sb = _summary_score(a.summary), _summary_score(b.summary)
  if sa != sb:
    return a if sa > sb else b
  ta, tb = ensure_utc(a.timestamp), ensure_utc(b.timestamp)
  return a if ta >= tb else b


class _UnionFind:
  def __init__(self, n: int) -> None:
    self._p = list(range(n))

  def find(self, x: int) -> int:
    while self._p[x] != x:
      self._p[x] = self._p[self._p[x]]
      x = self._p[x]
    return x

  def union(self, a: int, b: int) -> None:
    ra, rb = self.find(a), self.find(b)
    if ra != rb:
      self._p[rb] = ra


def _pair_is_duplicate(a: "MacroNewsItem", b: "MacroNewsItem") -> bool:
  ca = canonicalize_url(a.url or "")
  cb = canonicalize_url(b.url or "")
  if ca and cb and ca == cb:
    return True

  na = normalize_title_for_cluster(a.title)
  nb = normalize_title_for_cluster(b.title)
  if not na or not nb:
    return False

  delta = abs(ensure_utc(a.timestamp) - ensure_utc(b.timestamp))
  if na == nb:
    return delta <= _IDENTICAL_MAX_DELTA

  toks_a = len(_title_tokens(na))
  toks_b = len(_title_tokens(nb))
  min_toks = min(toks_a, toks_b)
  if min_toks < _MIN_TOKENS_FOR_FUZZY:
    return False

  if delta > _FUZZY_MAX_DELTA:
    return False

  seq = _sequence_similarity(na, nb)
  jac = _token_jaccard(na, nb)
  if seq >= _FUZZY_SEQUENCE_THRESHOLD and jac >= 0.72:
    return True
  return False


def dedupe_macro_news_clusters(items: list["MacroNewsItem"]) -> list["MacroNewsItem"]:
  """
  Collapse near-duplicate MacroNewsItem rows; return one representative per cluster.
  Order of returned list is undefined — caller should sort.
  """
  if len(items) == 0:
    return []
  if len(items) == 1:
    return [items[0]]

  n = len(items)
  uf = _UnionFind(n)

  for i in range(n):
    for j in range(i + 1, n):
      if _pair_is_duplicate(items[i], items[j]):
        uf.union(i, j)

  clusters: dict[int, list[int]] = {}
  for i in range(n):
    r = uf.find(i)
    clusters.setdefault(r, []).append(i)

  out: list["MacroNewsItem"] = []
  for _root, idxs in clusters.items():
    members = [items[k] for k in idxs]
    best = members[0]
    for m in members[1:]:
      best = _better_representative(best, m)
    n_merged = len(members)
    if n_merged > 1:
      others = _related_publishers_others(members, best)
      best = replace(best, duplicate_count=n_merged, related_publishers=others)
    out.append(best)
  return out


def finalize_macro_news_list(
  items: list["MacroNewsItem"],
  limit: int,
) -> list["MacroNewsItem"]:
  """
  Full pipeline: cluster dedupe → sort (impact, tier, recency) → trim to limit.
  """
  deduped = dedupe_macro_news_clusters(items)
  return _sort_and_cap(deduped, limit)


def _sort_and_cap(items: list["MacroNewsItem"], limit: int) -> list["MacroNewsItem"]:
  def sk(x: "MacroNewsItem") -> tuple[float, float, float]:
    ts = ensure_utc(x.timestamp).timestamp()
    imp = x.impact
    if imp is not None:
      return (-float(imp), float(x.publisher_tier), -ts)
    return (0.0, float(x.publisher_tier), -ts)

  items.sort(key=sk)
  return items[:limit]
