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
    """True when one episode names every given name: in its text, its title or as its author.
    A chat message's title is its channel (#payments), which says where it was posted, not what it says."""
    title = "" if episode.get("channel") == "chat" else episode.get("title")
    haystack = "\n".join(str(v or "") for v in (episode.get("text"), title, episode.get("author")))
    return all(mentions(haystack, n) for n in names)


FIRST_PERSON = re.compile(r"\b(?:I|my|me)\b")  # case-sensitive on purpose: "I", not "i" in a list


def episode_states(episode: dict, cue: str, *names: str) -> bool:
    """True when one line of the episode names every given name and, if the relation has a cue (a regex such as
    r"\\bown" for OWNS), carries it. The title counts for every line (a runbook's title is its system), a chat message's
    title does not. The author counts as named only on a first-person line ("I am now the owner of billing-api") or for
    a relation with no cue: whoever writes "fixed X in billing-api" did the work, but writing a catalog does not make
    you a party to each of its lines."""
    title = "" if episode.get("channel") == "chat" else str(episode.get("title") or "")
    author = str(episode.get("author") or "")
    for line in str(episode.get("text") or "").splitlines() or [""]:
        who = author if not cue or FIRST_PERSON.search(line) else ""
        if all(mentions(f"{line}\n{title}\n{who}", n) for n in names) and (not cue or re.search(cue, f"{line}\n{title}", re.IGNORECASE)):
            return True
    return False


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
