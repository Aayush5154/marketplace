"""
validator/helpers.py

Text helpers, compiled regexes, and small utilities for the
Marketplace Listing Quality Reviewer.
"""

import re
from difflib import SequenceMatcher

from validator.constants import PLACEHOLDERS

# ============================================================
# COMPILED REGEXES
# ============================================================

PRICE_RE = re.compile(r"^[0-9]+(\.[0-9]{1,2})?$")

EMAIL_RE = re.compile(
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
    re.I,
)

URL_RE = re.compile(
    r"""
    (?:
        https?://
        |
        www\.
        |
        \b[\w-]+\.
        (?:com|in|net|org|io|co|shop|store)
        \b
    )
    """,
    re.I | re.VERBOSE,
)

PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{6,}\d")

HANDLE_RE = re.compile(r"(?<![\\w@])@[A-Za-z0-9_.]{3,}")

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F2FF"
    "\U00002B00-\U00002BFF"
    "]"
)

REPEATED_PUNCT_RE = re.compile(r"[!?]{2,}|([^\w\s])\1{2,}")


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    """
    Trim and collapse whitespace.

    Related policy:
        POL-3.8
    """
    if value is None:
        return ""

    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_title(text):
    """
    Normalize title for exact duplicate detection.

    Policy:
        POL-8.2

    Steps:
        1. lowercase
        2. remove punctuation
        3. collapse whitespace
    """
    text = clean_text(text).lower()

    # Remove punctuation.
    text = re.sub(r"[^\w\s]", "", text)

    # Collapse whitespace.
    return re.sub(r"\s+", " ", text).strip()


def get_attributes(listing):
    """
    Convert attributes into:

        {
            "brand": "Aurora",
            "condition": "New"
        }

    Accepts:

        dict
        list of "key: value"
        newline/semicolon separated string
    """

    attrs = listing.get("attributes") or {}

    # Example:
    # "brand: Aurora; condition: New"
    if isinstance(attrs, str):
        attrs = [
            item
            for item in re.split(r"[\n;]", attrs)
            if item.strip()
        ]

    # Example:
    # ["brand: Aurora", "condition: New"]
    if isinstance(attrs, list):
        parsed = {}

        for item in attrs:
            item = str(item)

            if ":" not in item:
                continue

            key, value = item.split(":", 1)

            parsed[key] = value

        attrs = parsed

    if not isinstance(attrs, dict):
        return {}

    return {
        clean_text(key).lower(): clean_text(value)
        for key, value in attrs.items()
    }


def result(
    check,
    passed,
    rules,
    message="",
    skipped=False,
):
    """
    Standard result object.
    """

    return {
        "check": check,
        "passed": passed,
        "skipped": skipped,
        "rules": rules,
        "message": message,
    }


def is_missing(value):
    """
    POL-2.3

    A field is considered missing when it contains:

    - empty value
    - whitespace only
    - placeholder text
    - repeated single characters
    """

    if isinstance(value, dict):
        return len(value) == 0

    text = clean_text(value)

    if not text:
        return True

    if text.lower() in PLACEHOLDERS:
        return True

    # Examples:
    # "aaaa"
    # "-----"
    # "111111"
    #
    # Only treat it as missing if there are no spaces and
    # the same character is repeated.
    if len(text) >= 3 and len(set(text)) == 1:
        return True

    return False


def similarity(a, b):
    return SequenceMatcher(
        None,
        normalize_title(a),
        normalize_title(b),
    ).ratio()


def _same_seller(a, b):
    return (
        clean_text(a.get("seller")).lower()
        ==
        clean_text(b.get("seller")).lower()
    )


def _has_phone(text):
    """
    Avoid flagging random short numbers.
    Requires at least 8 digits.
    """

    for match in PHONE_RE.finditer(text):

        digit_count = sum(
            character.isdigit()
            for character in match.group()
        )

        if digit_count >= 8:
            return True

    return False
