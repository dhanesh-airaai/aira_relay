"""Pure Metaphone-based phonetic helpers — no IO, no external state beyond the encoder."""

from __future__ import annotations

from typing import Any

from pyphonetics import Metaphone  # type: ignore[reportMissingTypeStubs]

_metaphone: Metaphone = Metaphone()


def get_phonetic_tags(query: str) -> list[str]:
    """Return a Metaphone phonetic tag for each whitespace-delimited word in *query*."""
    tags: list[str] = []
    for word in query.split():
        stripped = word.strip()
        if not stripped:
            continue
        tag: str = _metaphone.phonetics(stripped)  # type: ignore[reportUnknownMemberType]
        if tag:
            tags.append(tag)
    return tags


def extract_phonetic_entries(
    contacts: list[dict[str, Any]],
) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Extract ``(phonetic_tag, original_word, w_chat_id)`` tuples from contact names.

    Args:
        contacts: List of contact dicts.  Each must have ``id`` or ``w_chat_id``
                  and ``name`` or ``pushname``.

    Returns:
        A tuple of (phonetic_entries, key_words).  ``key_words`` is a flat list
        of every word seen — used to query Qdrant for existing entries.
    """
    phonetic_entries: list[tuple[str, str, str]] = []
    key_words: list[str] = []

    for contact in contacts:
        chat_name: str = contact.get("name") or contact.get("pushname") or ""
        w_chat_id: str = contact.get("id") or contact.get("w_chat_id") or ""
        if not chat_name or not w_chat_id:
            continue

        for word in chat_name.split():
            stripped = word.strip()
            if not stripped:
                continue
            key_words.append(stripped)
            tag: str = _metaphone.phonetics(stripped)  # type: ignore[reportUnknownMemberType]
            if tag:
                phonetic_entries.append((tag, stripped, w_chat_id))

    return phonetic_entries, key_words


def aggregate_by_key(
    phonetic_entries: list[tuple[str, str, str]],
) -> dict[str, tuple[str, set[str]]]:
    """Map each original word → ``(phonetic_tag, set_of_w_chat_ids)``."""
    key_to_data: dict[str, tuple[str, set[str]]] = {}
    for tag, word, w_chat_id in phonetic_entries:
        if word in key_to_data:
            key_to_data[word][1].add(w_chat_id)
        else:
            key_to_data[word] = (tag, {w_chat_id})
    return key_to_data


def intersect_id_sets(id_sets: list[set[str]]) -> set[str]:
    """Intersect multiple sets of w_chat_ids.

    Single-word queries → union of that word's matching IDs.
    Multi-word queries  → intersection (contact must match *all* query words).
    """
    if not id_sets:
        return set()
    if len(id_sets) == 1:
        return id_sets[0]
    result = id_sets[0]
    for s in id_sets[1:]:
        result = result.intersection(s)
    return result
