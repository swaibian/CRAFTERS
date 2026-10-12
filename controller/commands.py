"""Generic command-catalog middle layer: discover app capabilities by search.

The app's engine registry (``engine.commands`` reply) lists every function
the open document can be driven with — layers, blend modes, filters,
adjustments, text, selection, … Each entry carries an id, a label, its menu
path, a params doc and enablement. :class:`CommandCatalog` indexes that
registry once and answers natural keyword queries (``"rotate"``,
``"black and white"``, ``"blend"``, ``"duplicate layer"``) with ranked
entries, so planners discover what to do generically — there is no
phrase→command-id table anywhere in the stack.

Pure Python, no I/O: the service builds the catalog from one
``engine.commands`` reply per chat run; the agent loop uses
:meth:`CommandCatalog.suggest` for honest error hints and MockBrain uses
:meth:`CommandCatalog.search` + :func:`params_from_message` for
deterministic no-key planning.

SW-REQ: SW-REQ-STREAM (generic live capability discovery, TC-B).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

#: Query words with no discriminative power (politeness, articles, pronouns,
#: generic verbs and the ever-present nouns "picture"/"image"/…). Domain
#: nouns stay informative and are kept (``layer``, ``blend``, ``mode``,
#: ``opacity``, …). Applied to QUERY text only — entry text keeps every word.
_QUERY_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "all",
        "also",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "bit",
        "but",
        "by",
        "can",
        "canvas",
        "change",
        "changes",
        "could",
        "did",
        "do",
        "docs",
        "document",
        "documents",
        "does",
        "done",
        "every",
        "file",
        "files",
        "for",
        "from",
        "get",
        "got",
        "guess",
        "guessed",
        "here",
        "how",
        "i",
        "if",
        "image",
        "images",
        "in",
        "into",
        "is",
        "it",
        "its",
        "just",
        "like",
        "little",
        "made",
        "make",
        "makes",
        "may",
        "me",
        "maybe",
        "might",
        "must",
        "my",
        "need",
        "no",
        "not",
        "now",
        "of",
        "on",
        "once",
        "only",
        "onto",
        "open",
        "or",
        "our",
        "over",
        "perhaps",
        "photo",
        "photos",
        "picture",
        "pictures",
        "please",
        "quite",
        "rather",
        "really",
        "slight",
        "slightly",
        "small",
        "so",
        "some",
        "somewhat",
        "tell",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "think",
        "this",
        "those",
        "to",
        "too",
        "turn",
        "us",
        "use",
        "very",
        "want",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "yes",
        "you",
        "your",
    }
)

_ENUM_RE = re.compile(r'"(\w+)"\s*:\s*"([^"]+)"')
_NUMERIC_RANGE_RE = re.compile(r'"(\w+)"\s*:\s*-?\d+(?:\.\d+)?\s*\.\.')
_NUMERIC_TYPE_RE = re.compile(r'"(\w+)"\s*:\s*(?:number|int|i32|u64|float)')
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_WORD_SPLIT_RE = re.compile(r"[A-Za-z0-9]+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

#: Max length of the params string kept in compact search results; longer
#: schemas are head-truncated (search/ranking still sees the full text).
SHORT_PARAMS_LIMIT = 120

#: How far the fuzzy token tier may stray (small edit distance on long
#: tokens only).
_FUZZY_EDIT_LIMIT = 1


def _tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric word tokens in reading order.

    :param text: Raw text (query, label, schema, …).
    :returns: Tokens (may repeat; order preserved).
    """
    return [m.group(0).lower() for m in _WORD_SPLIT_RE.finditer(text)]


def _camel_words(text: str) -> list[str]:
    """Split identifier-ish text into words (dots/underscores + camelCase).

    ``"image.imageRotation.90cw"`` → ``["image", "image", "Rotation",
    "90cw"]`` (case preserved here; matching lowercases).

    :param text: Id, label, menu path or schema text.
    :returns: Word list.
    """
    return _WORD_SPLIT_RE.findall(_CAMEL_RE.sub(" ", text))


def keywords(text: str) -> list[str]:
    """Extract salient query keywords in message order (stopwords dropped).

    The query-side vocabulary for :meth:`CommandCatalog.search` and
    MockBrain planning: ``"make the picture black & white"`` →
    ``["black", "white"]``. Duplicates collapse to the first occurrence.

    :param text: User message / query text.
    :returns: Salient tokens, in order of first appearance.
    """
    seen: set[str] = set()
    out: list[str] = []
    for token in _tokenize(text):
        if token in _QUERY_STOPWORDS or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _levenshtein(a: str, b: str, cap: int = 48) -> int:
    """Edit distance with an input cap (registry ids are short).

    :param a: First string.
    :param b: Second string.
    :param cap: Compare at most this many leading chars each.
    :returns: Insert/delete/substitute distance (or ``2 * cap`` when the
        capped strings differ wildly).
    """
    a, b = a[:cap], b[:cap]
    if a == b:
        return 0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (ca != cb),
                )
            )
        previous = current
    return previous[-1]


def _tokens_match(query_token: str, entry_token: str) -> str:
    """Match quality between one query token and one entry token.

    :param query_token: Lowercased query token.
    :param entry_token: Lowercased entry token.
    :returns: ``"exact"``, ``"prefix"`` (near-prefix — ``"rotate"``
        ↔``"rotation"``, ``"blend"``↔``"blending"``, ``"bright"``
        ↔``"brightness"``), ``"fuzzy"`` (1-edit on long tokens —
        ``"bright"``↔``"right"``) or ``""`` for no match. Prefix beats
        fuzzy: a near-miss spelling of a name should not tie with an
        unrelated word that happens to be one edit away.
    """
    if query_token == entry_token:
        return "exact"
    shorter, longer = sorted((query_token, entry_token), key=len)
    if len(shorter) >= 4:
        if longer.startswith(shorter) and len(shorter) >= len(longer) - 1:
            return "prefix"
        common = 0
        for qc, ec in zip(query_token, entry_token):
            if qc != ec:
                break
            common += 1
        if common >= 4 and common >= min(len(query_token), len(entry_token)) - 1:
            return "prefix"
        if (
            min(len(query_token), len(entry_token)) >= 5
            and _levenshtein(query_token, entry_token) <= _FUZZY_EDIT_LIMIT
        ):
            return "fuzzy"
    return ""


def _params_text(raw: Any) -> str:
    """Normalize a raw params field into a string.

    Engine registry entries carry a JSON-ish schema string; stubs and other
    transports may send a dict (or nothing). Never raises.

    :param raw: Raw ``params`` field (any shape).
    :returns: Schema text (``""`` when absent/unusable).
    """
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, Mapping):
        try:
            return json.dumps(dict(raw), separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            return ""
    return ""


def _short(text: str, limit: int) -> str:
    """Head-truncate ``text`` to ``limit`` chars (ellipsis when cut)."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _normalize_entry(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one registry entry, tolerating unknown/missing fields.

    Accepts the engine shape (``id``, ``label``, ``menu`` list, ``params``
    string, ``enabled`` bool) plus common spellings (``command``/``name``
    for the id, ``name``/``title`` for the label, menu as a string, params
    as a dict, ``available`` for ``enabled``). Extra fields are ignored.

    :param raw: Raw entry mapping.
    :returns: ``{id, label, enabled, params, menu}`` (``enabled`` is None
        when the reply does not say) or ``{}`` when no id can be found.
    """
    if not isinstance(raw, Mapping):
        return {}
    entry_id = raw.get("id") or raw.get("command") or raw.get("commandId") or ""
    if not isinstance(entry_id, str) or not entry_id.strip():
        return {}
    label_raw = raw.get("label") or raw.get("title") or raw.get("name") or ""
    label = label_raw.strip() if isinstance(label_raw, str) else str(label_raw)
    enabled_raw = raw.get("enabled", raw.get("available"))
    enabled = bool(enabled_raw) if isinstance(enabled_raw, bool) else None
    menu_raw = (
        raw.get("menu")
        or raw.get("menu_path")
        or raw.get("menuPath")
        or raw.get("path")
        or ""
    )
    if isinstance(menu_raw, (list, tuple)):
        menu = " / ".join(str(part) for part in menu_raw)
    elif isinstance(menu_raw, str):
        menu = menu_raw
    else:
        menu = str(menu_raw)
    params = _params_text(
        raw.get("params", raw.get("parameters", raw.get("param", "")))
    )
    return {
        "id": entry_id.strip(),
        "label": label,
        "enabled": enabled,
        "params": params,
        "menu": menu,
    }


def _entries_list(entries: Any) -> list[Any]:
    """Accept a bare entry list or a wrapped ``engine.commands`` reply.

    :param entries: List of entry dicts, or an envelope dict
        (``{"commands": [...]}`` / ``{"value": [...]}`` / ``{"result": [...]}``
        / ``{"id": ..., "ok": ..., "result": [...]}``).
    :returns: The raw entry list (possibly empty).
    """
    if isinstance(entries, Mapping):
        for key in ("commands", "value", "result"):
            found = entries.get(key)
            if isinstance(found, list):
                return found
        return []
    if isinstance(entries, Iterable) and not isinstance(entries, (str, bytes)):
        return list(entries)
    return []


def params_from_message(params_doc: str, message: str) -> dict[str, Any]:
    """Infer command params from a message using the command's own schema.

    Fully generic — no per-command knowledge. Two schema-driven rules:

    1. Quoted enumerations (``"blend":"Normal|Multiply|Screen|…"``) fill in
       when one of the listed values appears as a word/phrase in the message
       (``"set the blend mode to multiply"`` → ``{"blend": "Multiply"}`` —
       the schema's own casing is kept).
    2. Numbers fill numeric keys (``"opacity":0..1?``): a numeric key named
       in the message wins (``"opacity 50"`` → ``{"opacity": 50}``); with no
       named key, a lone message number fills the schema's only numeric key.

    Everything else (nested objects, colors, points) is left to the real
    planner, which reads the schema verbatim.

    :param params_doc: The command's params schema text (JSON-ish doc).
    :param message: User message.
    :returns: Params mapping (possibly empty).
    """
    params: dict[str, Any] = {}
    lowered = message.lower()
    for match in _ENUM_RE.finditer(params_doc):
        key, alts_raw = match.group(1), match.group(2)
        for alt in alts_raw.split("|"):
            alt = alt.strip()
            if len(alt) < 2 or alt.startswith(("…", "...")):
                continue
            if re.search(r"(?<!\w)" + re.escape(alt.lower()) + r"(?!\w)", lowered):
                params[key] = alt
                break
    numbers = [float(n) if "." in n else int(n) for n in _NUMBER_RE.findall(message)]
    if not numbers:
        return params
    numeric_keys = {
        match.group(1)
        for match in (
            *_NUMERIC_RANGE_RE.finditer(params_doc),
            *_NUMERIC_TYPE_RE.finditer(params_doc),
        )
    }
    if not numeric_keys:
        return params
    message_tokens = set(_tokenize(message))
    named = [key for key in numeric_keys if key.lower() in message_tokens]
    if len(named) == 1:
        params[named[0]] = numbers[0]
    elif not named and len(numeric_keys) == 1 and len(numbers) == 1:
        params[next(iter(numeric_keys))] = numbers[0]
    return params


class CommandCatalog:
    """Searchable index over one app command registry (generic middle layer).

    Built from an ``engine.commands`` reply (list of entry dicts; envelope
    dicts and missing/unknown fields are tolerated). Entries keep their
    full params schema for matching; :meth:`search` returns compact
    ``{id, label, enabled, params}`` dicts ready for prompt/hint use.

    Ranking is token-based over id + label + menu path + params doc, in
    tiers — exact id, then id substring, then exact token matches (label/id
    words like ``"duplicate"`` or ``"clockwise"``), then fuzzy token
    matches (``"rotate"``↔``"rotation"``). Ties break on more matched query
    tokens, then the shorter id, then id order — fully deterministic.

    :param entries: ``engine.commands`` reply (list or envelope) or None.
    """

    def __init__(
        self,
        entries: Iterable[Mapping[str, Any]] | Mapping[str, Any] | None = None,
    ) -> None:
        records: list[dict[str, Any]] = []
        for raw in _entries_list(entries):
            record = _normalize_entry(raw)
            if not record:
                continue
            record["_query"] = " ".join(
                [record["id"], record["label"], record["menu"], record["params"]]
            ).lower()
            record["_tokens"] = {
                token.lower()
                for token in _camel_words(
                    " ".join(
                        [
                            record["id"],
                            record["label"],
                            record["menu"],
                            record["params"],
                        ]
                    )
                )
            }
            records.append(record)
        self._entries = records

    def __len__(self) -> int:
        return len(self._entries)

    def params_doc(self, command_id: str) -> str:
        """Full params schema text for one id (``""`` when unknown).

        :param command_id: Registry command id.
        :returns: Verbatim schema text (not the short compact form).
        """
        for record in self._entries:
            if record["id"] == command_id:
                return record["params"]
        return ""

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Rank registry entries for a natural keyword query.

        Token-based and case-insensitive; stopwords are dropped from the
        query (``"make the picture black and white"`` → ``["black",
        "white"]``). Tier order — exact id > id substring > name-field
        hits (exact/prefix tokens in id or label — the query named the
        tool) > weaker evidence (fuzzy name hits, or words that appear
        only inside a params schema) — then more matched query tokens,
        higher weighted score, shorter id, id order.

        :param query: Free-text query (e.g. ``"blend"``, ``"duplicate
            layer"``, ``"black and white"``).
        :param limit: Max entries returned (default 20).
        :returns: Compact entries ``{id, label, enabled, params}`` (params
            as a short string — verbatim schema when small, head-truncated
            when huge). Empty for a query with no salient tokens or no
            match.
        """
        tokens = keywords(query)
        if not tokens and not query.strip():
            return []
        query_compact = re.sub(r"[^a-z0-9]+", "", query.lower())
        ranked: list[tuple[int, int, int, int, str]] = []
        for record in self._entries:
            tier, matched, score = self._score(record, tokens, query, query_compact)
            if tier <= 0:
                continue
            ranked.append((-tier, -matched, -score, len(record["id"]), record["id"]))
        ranked.sort()
        out: list[dict[str, Any]] = []
        for _tier, _matched, _score, _id_len, command_id in ranked[: max(limit, 0)]:
            record = next(r for r in self._entries if r["id"] == command_id)
            out.append(
                {
                    "id": record["id"],
                    "label": record["label"],
                    "enabled": record["enabled"],
                    "params": _short(record["params"], SHORT_PARAMS_LIMIT),
                }
            )
        return out

    def _score(
        self,
        record: Mapping[str, Any],
        tokens: list[str],
        query: str,
        query_compact: str,
    ) -> tuple[int, int, int]:
        """Tier/matched/score triple for one entry (see :meth:`search`).

        Tier 2 = the query named the tool (an exact/prefix token hit on
        id/label); tier 1 = weaker evidence (a fuzzy name hit, or exact
        words only inside the params schema — e.g. "curves" appearing in
        Camera Raw's schema text must not outrank the Curves command).
        """
        id_compact = re.sub(r"[^a-z0-9]+", "", record["id"].lower())
        if query_compact and query_compact == id_compact:
            return 4, len(tokens), 1000
        if (
            query_compact
            and len(query_compact) >= 3
            and (query_compact in id_compact or id_compact in query_compact)
        ):
            return 3, len(tokens), 800
        if not tokens:
            return 0, 0, 0
        id_tokens = {t.lower() for t in _camel_words(record["id"])}
        label_words = [t.lower() for t in _camel_words(record["label"])]
        label_tokens = set(label_words)
        menu_tokens = {t.lower() for t in _camel_words(record["menu"])}
        params_tokens = {t.lower() for t in _camel_words(record["params"])}
        matched = 0
        score = 0
        name_hit = False
        for token in tokens:
            best = 0
            for field_tokens, exact_w, prefix_w, fuzzy_w, is_name in (
                (id_tokens, 60, 45, 30, True),
                (label_tokens, 40, 30, 20, True),
                (menu_tokens, 15, 11, 8, False),
                (params_tokens, 10, 7, 5, False),
            ):
                quality = max(
                    (_tokens_match(token, other) for other in field_tokens),
                    key=lambda q: {"": 0, "fuzzy": 1, "prefix": 2, "exact": 3}[q],
                    default="",
                )
                if quality == "exact":
                    best = max(best, exact_w)
                elif quality == "prefix":
                    best = max(best, prefix_w)
                elif quality == "fuzzy":
                    best = max(best, fuzzy_w)
                if is_name and quality in ("exact", "prefix"):
                    name_hit = True
            if best:
                matched += 1
                score += best
                if token in id_tokens:
                    # Whole id segment matched ("curves" in
                    # image.adjustments.curves) — the query named this tool.
                    score += 30
        if not matched:
            return 0, 0, 0
        if matched == len(tokens):
            score += 50
        if label_words:
            covered = sum(
                1 for word in label_words if any(_tokens_match(t, word) for t in tokens)
            )
            score += int(40 * covered / len(label_words))
        tier = 2 if name_hit else 1
        return tier, matched, score

    def suggest(self, unknown_id: str, limit: int = 3) -> list[str]:
        """Nearest registry ids for a rejected id (error-message hints).

        Shared-token score over id + label words (exact token = 2, fuzzy
        near-token = 1 — ``"90cc"`` leans toward ``90ccw``), then edit
        distance between the ids — ``"image.adjustments.desatur"`` suggests
        ``"image.adjustments.desaturate"``. Zero-signal garbage returns
        ``[]`` instead of noise.

        :param unknown_id: The id the app rejected.
        :param limit: Max suggestions (default 3).
        :returns: Nearest ids (best first).
        """
        cleaned = str(unknown_id or "").strip()
        if not cleaned:
            return []
        query_tokens = [t.lower() for t in _camel_words(cleaned)]
        ranked: list[tuple[int, int, int, str]] = []
        quality_rank = {"": 0, "fuzzy": 1, "prefix": 2, "exact": 3}
        for record in self._entries:
            shared = 0
            for token in query_tokens:
                quality = max(
                    (_tokens_match(token, other) for other in record["_tokens"]),
                    key=lambda q: quality_rank[q],
                    default="",
                )
                shared += quality_rank[quality]
            dist = _levenshtein(cleaned.lower(), record["id"].lower())
            if shared <= 0 and dist > 8:
                continue
            ranked.append((-shared, dist, len(record["id"]), record["id"]))
        ranked.sort()
        return [command_id for *_, command_id in ranked[: max(limit, 0)]]

    @staticmethod
    def render(entry: Mapping[str, Any]) -> str:
        """One short human line for prompt/hint use.

        ``image.adjustments.desaturate — Desaturate ({}) [disabled]`` —
        em-dash before the label, short params in parens (omitted when
        empty), ``[disabled]`` only when the registry says so.

        :param entry: Raw or compact entry mapping.
        :returns: One line (no trailing newline).
        """
        record = _normalize_entry(entry)
        if not record:
            return ""
        line = record["id"]
        if record["label"]:
            line += f" — {record['label']}"
        params = _short(record["params"], SHORT_PARAMS_LIMIT)
        if params:
            line += f" ({params})"
        if record["enabled"] is False:
            line += " [disabled]"
        return line

    @staticmethod
    def render_list(entries: Iterable[Mapping[str, Any]]) -> str:
        """Render entries as newline-joined :meth:`render` lines.

        :param entries: Entry mappings (raw or compact).
        :returns: One line per entry (``""`` for none).
        """
        return "\n".join(
            line for line in (CommandCatalog.render(entry) for entry in entries) if line
        )


__all__ = [
    "SHORT_PARAMS_LIMIT",
    "CommandCatalog",
    "keywords",
    "params_from_message",
]
