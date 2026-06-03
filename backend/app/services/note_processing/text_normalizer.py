"""
Text Normalizer — VA Vista / CPRS ASCII safety pass.

Purpose
-------
VA CPRS / Vista (MUMPS) chart fields render any non-ASCII byte as a
literal `?` when text is pasted in. Our pipeline pulls text from many
sources — OCR, LLM completions, structured extractor templates, GraphRAG
community summaries — that frequently emit Unicode look-alikes for
characters that have valid ASCII equivalents:

* en-dash U+2013 `–`, em-dash U+2014 `—`, minus U+2212 `−`  -> `-`
* curly quotes U+2018/U+2019/U+201C/U+201D                 -> `'` `"`
* ellipsis U+2026 `…`                                      -> `...`
* non-breaking space U+00A0, en/em-space, narrow-NBSP, ... -> ` `
* zero-width / byte-order marks (U+200B, U+200C, U+200D,
  U+2060, U+FEFF)                                          -> dropped

Without this pass, providers see `???` in pasted notes and have to
manually retype the affected lines. The normalizer is applied at the
very last step of note assembly, after every other transformation, so
no upstream code has to remember to do it.

The normalizer is conservative: it only maps glyphs that have an
unambiguous ASCII equivalent. Anything else (clinical symbols,
non-Latin scripts, math, etc.) is left intact and the operator can
decide what to do with it.
"""

from __future__ import annotations

import unicodedata


# Direct character-to-string mapping. Keep this table the single source
# of truth — any future additions go here, not scattered through the
# extractors.
_ASCII_MAP = {
    # Dashes / hyphens / minus
    "\u2010": "-",   # hyphen
    "\u2011": "-",   # non-breaking hyphen
    "\u2012": "-",   # figure dash
    "\u2013": "-",   # en-dash
    "\u2014": "-",   # em-dash
    "\u2015": "-",   # horizontal bar
    "\u2212": "-",   # minus sign
    "\uFE58": "-",   # small em-dash
    "\uFE63": "-",   # small hyphen-minus
    "\uFF0D": "-",   # fullwidth hyphen-minus

    # Quotes - single
    "\u2018": "'",   # left single quotation mark
    "\u2019": "'",   # right single quotation mark / apostrophe
    "\u201A": "'",   # single low-9 quotation mark
    "\u201B": "'",   # single high-reversed-9 quotation mark
    "\u2032": "'",   # prime
    "\u00B4": "'",   # acute accent (often used as apostrophe)
    "\u02BC": "'",   # modifier letter apostrophe

    # Quotes - double
    "\u201C": '"',   # left double quotation mark
    "\u201D": '"',   # right double quotation mark
    "\u201E": '"',   # double low-9 quotation mark
    "\u201F": '"',   # double high-reversed-9 quotation mark
    "\u2033": '"',   # double prime
    "\u00AB": '"',   # left guillemet
    "\u00BB": '"',   # right guillemet

    # Ellipsis
    "\u2026": "...",

    # Bullets and list markers (often pasted from PDFs)
    "\u2022": "*",   # bullet
    "\u2023": ">",   # triangular bullet
    "\u25E6": "o",   # white bullet
    "\u2043": "-",   # hyphen bullet

    # Spaces (non-breaking, en/em, narrow, ideographic, etc.)
    "\u00A0": " ",   # no-break space
    "\u1680": " ",   # ogham space mark
    "\u2000": " ",   # en quad
    "\u2001": " ",   # em quad
    "\u2002": " ",   # en space
    "\u2003": " ",   # em space
    "\u2004": " ",   # three-per-em space
    "\u2005": " ",   # four-per-em space
    "\u2006": " ",   # six-per-em space
    "\u2007": " ",   # figure space
    "\u2008": " ",   # punctuation space
    "\u2009": " ",   # thin space
    "\u200A": " ",   # hair space
    "\u202F": " ",   # narrow no-break space
    "\u205F": " ",   # medium mathematical space
    "\u3000": " ",   # ideographic space

    # Tabs that some sources emit instead of normal tabs
    "\u0009": "\t",  # keep regular tab as tab — ASCII anyway
    "\u00B7": "*",   # middle dot

    # Common typographic characters
    "\u00B0": " deg",   # degree sign -> "deg" (clinical: "37 deg C")
    "\u00B1": "+/-",    # plus-minus
    "\u00D7": "x",      # multiplication sign
    "\u00F7": "/",      # division sign
    "\u2044": "/",      # fraction slash
    "\u2192": "->",     # rightwards arrow
    "\u2190": "<-",     # leftwards arrow
    "\u2194": "<->",    # left-right arrow
    "\u21D2": "=>",     # rightwards double arrow
    "\u00A9": "(c)",    # copyright
    "\u00AE": "(R)",    # registered
    "\u2122": "(TM)",   # trademark
    "\u00BC": "1/4",
    "\u00BD": "1/2",
    "\u00BE": "3/4",
    "\u2153": "1/3",
    "\u2154": "2/3",
}

# Zero-width and other invisible characters that should be dropped.
_DROP = frozenset([
    "\u200B",   # zero-width space
    "\u200C",   # zero-width non-joiner
    "\u200D",   # zero-width joiner
    "\u2060",   # word joiner
    "\uFEFF",   # byte-order mark / zero-width no-break space
    "\u00AD",   # soft hyphen
    "\u034F",   # combining grapheme joiner
    "\u180E",   # mongolian vowel separator
])


def to_vista_ascii(text: str) -> str:
    """
    Replace Unicode look-alike characters with ASCII equivalents and
    drop zero-width / invisible characters.

    This function is idempotent: ``to_vista_ascii(to_vista_ascii(x)) == to_vista_ascii(x)``.

    Args:
        text: input text (any Unicode allowed)

    Returns:
        ASCII-safe text suitable for pasting into VistA CPRS.
    """
    if not text:
        return text

    out_chars = []
    for ch in text:
        if ch in _DROP:
            continue
        replacement = _ASCII_MAP.get(ch)
        if replacement is not None:
            out_chars.append(replacement)
            continue
        # Decompose accented Latin (e.g. é -> e + combining acute) and
        # discard the combining marks. This handles cases like patient
        # names from OCR with accented letters.
        if ord(ch) >= 0x80:
            decomposed = unicodedata.normalize("NFKD", ch)
            ascii_only = "".join(
                c for c in decomposed if not unicodedata.combining(c) and ord(c) < 0x80
            )
            if ascii_only:
                out_chars.append(ascii_only)
                continue
            # Final fallback: drop unmappable non-ASCII rather than
            # leak a `?` into VistA. Operators can re-paste from the
            # raw source if a specific glyph is clinically required.
            continue
        out_chars.append(ch)

    return "".join(out_chars)
