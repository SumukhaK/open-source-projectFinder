"""Bounded GitHub keyword compilation shared by legacy and hybrid search."""

import re
import unicodedata
from dataclasses import dataclass

GITHUB_SCOPE = "in:name,description,readme is:public archived:false"
MAX_KEYWORDS = 6
MAX_QUERY_CHARS = 256
MAX_CANDIDATES = 100
STOP_WORDS = frozenset(
    {
        "i",
        "a",
        "an",
        "the",
        "to",
        "and",
        "for",
        "with",
        "my",
        "want",
        "build",
        "create",
        "app",
        "that",
        "is",
        "of",
        "using",
    }
)
_FILTER_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._+#-]{0,63}$")


def keyword_text(idea):
    # Keep letters, digits and combining marks of any script; anything else separates words.
    return "".join(
        char
        if char in "_-" or char.isalnum() or unicodedata.category(char).startswith("M")
        else " "
        for char in idea.lower()
    )


def compile_keyword_query(idea):
    words = [word for word in keyword_text(idea).split() if word not in STOP_WORDS]
    words = words[:MAX_KEYWORDS]
    if not words:
        return None, "empty"
    query = " ".join(words)
    if len(query) > MAX_QUERY_CHARS:
        return None, "too_long"
    return query, None


@dataclass(frozen=True)
class CandidateFilters:
    """Only filters both sources can enforce with typed values."""

    language: str | None = None
    license: str | None = None

    def __post_init__(self):
        for name in ("language", "license"):
            value = getattr(self, name)
            if value is None:
                continue
            if not isinstance(value, str) or not _FILTER_VALUE.fullmatch(value.strip()):
                raise ValueError(f"Unsupported {name} filter")
            object.__setattr__(self, name, value.strip())


def _qualifier(name, value):
    # GitHub accepts quoted values for multi-word qualifiers; the strict value
    # pattern above already excludes quotes, colons and control characters.
    return f'{name}:"{value}"' if " " in value else f"{name}:{value}"


def filter_qualifiers(filters=None):
    if filters is None:
        return ""
    parts = [
        _qualifier(name, value)
        for name, value in (
            ("language", filters.language),
            ("license", filters.license),
        )
        if value
    ]
    return " " + " ".join(parts) if parts else ""


def keyword_search_params(idea, filters=None):
    query, problem = compile_keyword_query(idea)
    if problem:
        return None, problem
    return {
        "q": f"{query} {GITHUB_SCOPE}{filter_qualifiers(filters)}",
        "per_page": MAX_CANDIDATES,
        "page": 1,
    }, None
