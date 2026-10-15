"""Name matching shared by the write gate (grounding), the extractor and the ingest step (MENTIONS).

A name matches as a whole word, case-insensitively: "auth" is in "auth is flaky" and not in "Author: Ana",
and "billing-api" is not inside "billing-api-v2".
"""

from __future__ import annotations

import re


def _pattern(name: str) -> str:
    return r"(?<![\w-])" + re.escape(name) + r"(?![\w-])"


def mentions(text: str, name: str) -> bool:
    return bool(name) and re.search(_pattern(name), text, re.IGNORECASE) is not None


def episode_mentions(episode: dict, *names: str) -> bool:
    """True when one episode names every given name: in its text, its title or as its author."""
    haystack = "\n".join(str(episode.get(k) or "") for k in ("text", "title", "author"))
    return all(mentions(haystack, n) for n in names)


class NameIndex:
    """Known entity names by label, with one compiled matcher over all of them."""

    def __init__(self) -> None:
        self._names: dict[str, set[str]] = {}
        self._matcher: re.Pattern | None = None

    def __len__(self) -> int:
        return sum(len(v) for v in self._names.values())

    def add(self, label: str, name: str) -> None:
        if name and name not in self._names.setdefault(label, set()):
            self._names[label].add(name)
            self._matcher = None

    def names(self, label: str) -> set[str]:
        return set(self._names.get(label, ()))

    def labels_of(self, name: str) -> list[str]:
        return [label for label, names in self._names.items() if name in names]

    def find(self, text: str) -> list[tuple[str, str]]:
        """(label, name) of every known name that appears in the text, each once, in a stable order."""
        if self._matcher is None:
            every = sorted({n for names in self._names.values() for n in names}, key=lambda n: (-len(n), n))
            self._matcher = re.compile("|".join(_pattern(n) for n in every), re.IGNORECASE) if every else re.compile(r"(?!)")
        lower = {n.lower(): n for names in self._names.values() for n in names}
        found = {lower[m.group().lower()] for m in self._matcher.finditer(text)}
        return sorted((label, n) for label, names in self._names.items() for n in names if n in found)
