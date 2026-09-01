"""Portable lexical normalization for multilingual FTS experiments."""

import re

_TERM = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]", re.IGNORECASE)


def lexical_terms(text: str) -> list[str]:
    """Return lowercase words plus adjacent CJK bigrams for SQLite FTS5."""

    raw = _TERM.findall(text.lower())
    terms = list(raw)
    cjk_run: list[str] = []
    for term in [*raw, ""]:
        if len(term) == 1 and "\u3400" <= term <= "\u9fff":
            cjk_run.append(term)
            continue
        terms.extend("".join(cjk_run[index : index + 2]) for index in range(len(cjk_run) - 1))
        cjk_run = []
    return terms


def lexical_text(text: str) -> str:
    return " ".join(lexical_terms(text))


def fts_query(text: str) -> str:
    terms = lexical_terms(text)
    return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)
