"""Shared NLP utilities for keyword matching."""

import re
from typing import Iterable

# Pre-compiled pattern cache for word_match
_WORD_PATTERN_CACHE: dict[str, re.Pattern] = {}


def word_match(keyword: str, text: str) -> bool:
    """Match keyword as a whole word (not inside another word)."""
    if keyword not in _WORD_PATTERN_CACHE:
        _WORD_PATTERN_CACHE[keyword] = re.compile(
            rf'\b{re.escape(keyword)}\b', re.IGNORECASE
        )
    return bool(_WORD_PATTERN_CACHE[keyword].search(text))


def any_word_match(keywords: Iterable[str], text: str) -> bool:
    """Return True if any keyword matches as a whole word in text."""
    return any(word_match(kw, text) for kw in keywords)


def any_phrase_in(phrases: Iterable[str], text: str) -> bool:
    """Substring match for multi-word phrases."""
    return any(phrase in text for phrase in phrases)
