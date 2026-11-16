"""Text compared the way people read it: case and accents ignored, any alphabet kept.

"Κατάσταση", "κατασταση" and "ΚΑΤΑΣΤΑΣΗ" fold to the same text, as do "Estado" and "estado";
Greek, Latin and other letters all survive (unlike an a-z filter, which empties Greek names).
"""

from __future__ import annotations

import re
import unicodedata

_NOT_WORD = re.compile(r"[\W_]+")


def fold(text: str) -> str:
    """Lower case without accents or tonos marks."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def words(text: str) -> str:
    """Folded, with everything that is not a letter or digit turned into single spaces."""
    return _NOT_WORD.sub(" ", fold(text)).strip()
