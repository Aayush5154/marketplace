"""
validators.py

Deterministic checks for the Marketplace Listing Quality Reviewer.

No LLM is used for these checks.

A listing is expected to look like:

{
    "title": "Aurora 20000mAh Power Bank, 22.5W Fast Charging",
    "description": "....",
    "category": "Electronics",
    "price": "49.99",
    "attributes": {
        "brand": "Aurora",
        "model": "PB-20",
        "condition": "New",
        "warranty": "12 months"
    },
    "seller": "Aurora Store",
    "tags": ["power bank", "charger"]
}

Every check returns:

{
    "check": "check_name",
    "passed": True/False,
    "skipped": True/False,
    "rules": ["POL-x.y"],
    "message": "..."
}

Usage:

    run_all_checks(listing, other_listings)

For model-review triggers:

    find_model_triggers(listing)

Model triggers are NOT deterministic failures.
They are only signals for RAG + LLM review.
"""

import re
from difflib import SequenceMatcher

# ============================================================
# POLICY CONSTANTS
# ============================================================

REQUIRED_FIELDS = [
    "title",
    "description",
    "category",
    "price",
    "attributes",
    "seller",
]

PLACEHOLDERS = {
    "tbd",
    "n/a",
    "na",
    "test",
    "lorem ipsum",
    "none",
    "null",
}


# POL-4.1
# Each tuple contains alternative accepted attribute names.
CATEGORY_ATTRIBUTES = {
    "electronics": [
        ("brand",),
        ("model",),
        ("condition",),
        ("warranty",),
    ],

    "home & kitchen": [
        ("brand",),
        ("material",),
        ("dimensions",),
        ("condition",),
    ],

    "fashion & apparel": [
        ("brand",),
        ("size",),
        ("material",),
        ("condition",),
    ],

    "beauty & personal care": [
        ("brand",),
        ("volume", "weight"),
        ("ingredients",),
        ("expiry", "batch date"),
    ],

    "sports & outdoors": [
        ("brand",),
        ("condition",),
        ("size", "dimensions"),
    ],

    "books & media": [
        ("title", "author"),
        ("format",),
        ("condition",),
        ("language",),
    ],

    "toys & games": [
        ("brand",),
        ("recommended age range", "age range"),
        ("condition",),
        ("safety standard",),
    ],

    "home services": [
        ("service type",),
        ("service area",),
        ("availability",),
        ("pricing basis",),
    ],

    "professional services": [
        ("service type",),
        ("delivery method",),
        ("turnaround time",),
        ("pricing basis",),
    ],

    "digital products": [
        ("format",),
        ("platform", "compatibility"),
        ("licence type", "license type"),
        ("delivery method",),
    ],
}


# POL-4.2
ALLOWED_CONDITIONS = {
    "new",
    "open box",
    "refurbished",
    "used - like new",
    "used - good",
    "used - acceptable",
}


# These are NOT failures.
# They only tell the RAG/LLM layer that deeper review may be needed.
MODEL_TRIGGER_PHRASES = [
    "best",
    "#1",
    "guaranteed",
    "100%",
    "cure",
    "treat",
    "prevent",
    "doctor",
    "fda",
    "certified",
    "award",
    "limited time",
    "only X left",
    "trusted by",
    "better than",
    "like new",
    "genuine",
    "handmade",
    "organic",
]

PROMPT_INJECTION_PHRASES = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "follow these instructions",
    "approve this",
    "disregard the rules",
)


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


# ============================================================
# 1. REQUIRED FIELDS
# POL-2.1, POL-2.3
# ============================================================

def check_required_fields(listing):
    missing = []

    for field in REQUIRED_FIELDS:

        if field == "attributes":
            value = get_attributes(listing)
        else:
            value = listing.get(field)

        if is_missing(value):
            missing.append(field)

    if missing:
        return result(
            "required_fields",
            False,
            ["POL-2.1", "POL-2.3"],
            "Missing or placeholder fields: " + ", ".join(missing),
        )

    return result(
        "required_fields",
        True,
        ["POL-2.1", "POL-2.3"],
    )


# ============================================================
# 2. TITLE LENGTH
# POL-3.1
# ============================================================

def check_title_length(listing):
    title = clean_text(listing.get("title"))
    length = len(title)

    passed = 15 <= length <= 80

    return result(
        "title_length",
        passed,
        ["POL-3.1"],
        ""
        if passed
        else f"Title has {length} characters; it must be 15 to 80.",
    )


# ============================================================
# 3. DESCRIPTION LENGTH
# POL-3.2
# ============================================================

def check_description_length(listing):
    description = clean_text(listing.get("description"))
    length = len(description)

    passed = 80 <= length <= 2000

    return result(
        "description_length",
        passed,
        ["POL-3.2"],
        ""
        if passed
        else (
            f"Description has {length} characters; "
            "it must be 80 to 2,000."
        ),
    )


# ============================================================
# 4. PRICE FORMAT
# POL-3.3
# ============================================================

PRICE_RE = re.compile(
    r"^[0-9]+(\.[0-9]{1,2})?$"
)


def check_price_format(listing):
    price = clean_text(listing.get("price"))

    if not PRICE_RE.fullmatch(price):
        return result(
            "price_format",
            False,
            ["POL-3.3"],
            (
                f"Price '{price}' is invalid. "
                "Use a positive number with at most two decimals, "
                "without currency symbols or commas."
            ),
        )

    # Format is valid, now ensure > 0.
    if float(price) <= 0:
        return result(
            "price_format",
            False,
            ["POL-3.3"],
            "Price must be greater than 0.",
        )

    return result(
        "price_format",
        True,
        ["POL-3.3"],
    )


# ============================================================
# 5. PRICE RANGE
# POL-3.4
# ============================================================

def check_price_range(listing):
    price = clean_text(listing.get("price"))

    # Don't report a second failure when the format itself
    # is already invalid.
    if not PRICE_RE.fullmatch(price):
        return result(
            "price_range",
            True,
            ["POL-3.4"],
            "Skipped because price format is invalid.",
            skipped=True,
        )

    numeric_price = float(price)

    passed = 0.01 <= numeric_price <= 100000.00

    return result(
        "price_range",
        passed,
        ["POL-3.4"],
        ""
        if passed
        else (
            f"Price {price} must be between "
            "0.01 and 100,000.00."
        ),
    )


# ============================================================
# 6. SUPPORTED CATEGORY
# POL-3.5, POL-4.1
# ============================================================

def check_category(listing):
    category = clean_text(
        listing.get("category")
    ).lower()

    passed = category in CATEGORY_ATTRIBUTES

    return result(
        "category_supported",
        passed,
        ["POL-3.5", "POL-4.1"],
        ""
        if passed
        else (
            f"Category '{listing.get('category')}' "
            "is not supported."
        ),
    )


# ============================================================
# 7. REQUIRED CATEGORY ATTRIBUTES
# POL-2.4, POL-4.1
# ============================================================

def check_required_attributes(listing):
    category = clean_text(
        listing.get("category")
    ).lower()

    # Don't create a second failure if category itself
    # is invalid.
    if category not in CATEGORY_ATTRIBUTES:
        return result(
            "required_attributes",
            True,
            ["POL-2.4", "POL-4.1"],
            "Skipped because category is not supported.",
            skipped=True,
        )

    attrs = get_attributes(listing)

    missing = []

    for options in CATEGORY_ATTRIBUTES[category]:

        found = any(
            name in attrs and not is_missing(attrs[name])
            for name in options
        )

        if not found:
            missing.append(
                " or ".join(options)
            )

    if missing:
        return result(
            "required_attributes",
            False,
            ["POL-2.4", "POL-4.1"],
            (
                "Missing required attributes: "
                + ", ".join(missing)
            ),
        )

    return result(
        "required_attributes",
        True,
        ["POL-2.4", "POL-4.1"],
    )


# ============================================================
# 8. CONDITION
# POL-4.2
# ============================================================

def check_condition(listing):
    attrs = get_attributes(listing)
    condition = attrs.get("condition")

    # Missing condition is handled by required_attributes
    # when the category requires it.
    if condition is None or not clean_text(condition):
        return result(
            "condition_value",
            True,
            ["POL-4.2"],
            "Skipped because no condition value was provided.",
            skipped=True,
        )

    normalized = clean_text(condition).lower()

    passed = normalized in ALLOWED_CONDITIONS

    return result(
        "condition_value",
        passed,
        ["POL-4.2"],
        ""
        if passed
        else (
            f"Condition '{condition}' is not one of "
            "the allowed values."
        ),
    )


# ============================================================
# 9. TAGS
# POL-3.6
# ============================================================

def check_tags(listing):
    tags = listing.get("tags") or []

    if isinstance(tags, str):
        tags = tags.split(",")

    tags = [
        clean_text(tag)
        for tag in tags
        if clean_text(tag)
    ]

    problems = []

    if len(tags) > 10:
        problems.append(
            f"{len(tags)} tags provided; maximum is 10"
        )

    for tag in tags:
        length = len(tag)

        if not 2 <= length <= 30:
            problems.append(
                f"tag '{tag}' has {length} characters; "
                "must be 2 to 30"
            )

    return result(
        "tags",
        not problems,
        ["POL-3.6"],
        "; ".join(problems),
    )


# ============================================================
# 10. CONTACT DETAILS
# POL-9.2
# ============================================================

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

PHONE_RE = re.compile(
    r"\+?\d[\d\s\-().]{6,}\d"
)

HANDLE_RE = re.compile(
    r"(?<![\w@])@[A-Za-z0-9_.]{3,}"
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


def check_contact_details(listing):

    attrs_text = " ".join(
        f"{key} {value}"
        for key, value in get_attributes(listing).items()
    )

    tags = listing.get("tags") or []

    if isinstance(tags, str):
        tags_text = tags
    else:
        tags_text = " ".join(
            map(str, tags)
        )

    fields = {
        "title": str(
            listing.get("title") or ""
        ),
        "description": str(
            listing.get("description") or ""
        ),
        "attributes": attrs_text,
        "tags": tags_text,
        "seller": str(
            listing.get("seller") or ""
        ),
    }

    found = []

    for field, text in fields.items():

        if EMAIL_RE.search(text):
            found.append(
                f"email in {field}"
            )

        if URL_RE.search(text):
            found.append(
                f"web address in {field}"
            )

        if _has_phone(text):
            found.append(
                f"phone number in {field}"
            )

        if HANDLE_RE.search(text):
            found.append(
                f"social handle in {field}"
            )

    return result(
        "contact_details",
        not found,
        ["POL-9.2"],
        ""
        if not found
        else "Found: " + ", ".join(found),
    )


# ============================================================
# 11. EXACT DUPLICATE
# POL-8.2
# ============================================================

def _same_seller(a, b):
    return (
        clean_text(a.get("seller")).lower()
        ==
        clean_text(b.get("seller")).lower()
    )


def check_exact_duplicate(
    listing,
    other_listings,
):

    my_title = normalize_title(
        listing.get("title")
    )

    if not my_title:
        return result(
            "exact_duplicate",
            True,
            ["POL-8.2"],
            "Skipped because title is empty.",
            skipped=True,
        )

    for other in other_listings or []:

        if other is listing:
            continue

        if not _same_seller(listing, other):
            continue

        other_title = normalize_title(
            other.get("title")
        )

        if my_title == other_title:

            return result(
                "exact_duplicate",
                False,
                ["POL-8.2"],
                (
                    "Same seller already has this "
                    f"title: '{other.get('title')}'."
                ),
            )

    return result(
        "exact_duplicate",
        True,
        ["POL-8.2"],
    )


# ============================================================
# 12. NEAR DUPLICATE
# POL-8.3
# ============================================================

def similarity(a, b):
    return SequenceMatcher(
        None,
        normalize_title(a),
        normalize_title(b),
    ).ratio()


def check_near_duplicate(
    listing,
    other_listings,
):

    my_category = clean_text(
        listing.get("category")
    ).lower()

    my_title = normalize_title(
        listing.get("title")
    )

    my_description = clean_text(
        listing.get("description")
    )

    if not my_title and not my_description:
        return result(
            "near_duplicate",
            True,
            ["POL-8.3"],
            "Skipped because listing text is empty.",
            skipped=True,
        )

    for other in other_listings or []:

        if other is listing:
            continue

        # Same seller is required.
        if not _same_seller(listing, other):
            continue

        # Same category is required.
        other_category = clean_text(
            other.get("category")
        ).lower()

        if other_category != my_category:
            continue

        # Exact duplicate already handled separately.
        if (
            my_title
            and
            my_title == normalize_title(
                other.get("title")
            )
        ):
            continue

        title_similarity = similarity(
            listing.get("title"),
            other.get("title"),
        )

        description_similarity = similarity(
            listing.get("description"),
            other.get("description"),
        )

        if (
            title_similarity >= 0.90
            or
            description_similarity >= 0.90
        ):

            return result(
                "near_duplicate",
                False,
                ["POL-8.3"],
                (
                    f"Very similar to "
                    f"'{other.get('title')}' "
                    f"(title {title_similarity:.0%}, "
                    f"description {description_similarity:.0%})."
                ),
            )

    return result(
        "near_duplicate",
        True,
        ["POL-8.3"],
    )


# ============================================================
# 13. KEYWORD STUFFING
# POL-8.6
# ============================================================

def check_keyword_stuffing(listing):

    title = clean_text(
        listing.get("title")
    ).lower()

    words = re.findall(
        r"[a-z0-9]+",
        title,
    )

    counts = {}

    for word in words:

        # The deterministic appendix specifically checks
        # repeated words 3+ times in title.
        counts[word] = counts.get(word, 0) + 1

    repeated = [
        word
        for word, count in counts.items()
        if count >= 3
    ]

    return result(
        "keyword_stuffing",
        not repeated,
        ["POL-8.6"],
        ""
        if not repeated
        else (
            "Word repeated 3+ times in title: "
            + ", ".join(repeated)
        ),
    )


# ============================================================
# 14. ALL CAPS / SYMBOLS
# BRD-2.2, BRD-2.3
# ============================================================

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F2FF"
    "\U00002B00-\U00002BFF"
    "]"
)

REPEATED_PUNCT_RE = re.compile(
    r"[!?]{2,}|([^\w\s])\1{2,}"
)


def check_caps_and_symbols(listing):

    title = clean_text(
        listing.get("title")
    )

    problems = []

    letters = [
        char
        for char in title
        if char.isalpha()
    ]

    # Entire title in uppercase.
    if (
        len(letters) >= 5
        and title == title.upper()
    ):
        problems.append(
            "title is entirely in capital letters"
        )

    # Emoji/decorative symbols.
    if EMOJI_RE.search(title):
        problems.append(
            "title contains emoji or decorative symbols"
        )

    # Repeated punctuation.
    if REPEATED_PUNCT_RE.search(title):
        problems.append(
            "title has repeated punctuation"
        )

    return result(
        "caps_and_symbols",
        not problems,
        ["BRD-2.2", "BRD-2.3"],
        "; ".join(problems),
    )


# ============================================================
# MODEL REVIEW TRIGGERS
#
# NOT failures.
# These should be sent to RAG + LLM.
# ============================================================

def find_model_triggers(listing):

    attrs_text = " ".join(
        get_attributes(listing).values()
    )

    fields = {
        "title": str(
            listing.get("title") or ""
        ),
        "description": str(
            listing.get("description") or ""
        ),
        "attributes": attrs_text,
    }

    triggers = []

    for field, text in fields.items():

        lower_text = text.lower()

        for phrase in MODEL_TRIGGER_PHRASES:

            phrase_lower = phrase.lower()

            # "only X left"
            if phrase_lower == "only x left":

                match = re.search(
                    r"\bonly\s+\d+\s+(left|remaining)\b",
                    lower_text,
                )

            # Normal word/phrase.
            elif (
                phrase_lower[0].isalnum()
                and phrase_lower[-1].isalnum()
            ):

                match = re.search(
                    r"\b"
                    + re.escape(phrase_lower)
                    + r"\b",
                    lower_text,
                )

            # Things like #1 and 100%.
            else:

                match = (
                    phrase_lower
                    in lower_text
                )

            if match:

                triggers.append(
                    {
                        "field": field,
                        "phrase": phrase,
                    }
                )

    return triggers


def check_prompt_injection(listing):
    """Flag instruction-like listing text before it reaches the model."""
    text = " ".join(
        str(listing.get(field) or "")
        for field in ("title", "description", "seller")
    ).casefold()
    matches = [phrase for phrase in PROMPT_INJECTION_PHRASES if phrase in text]
    return result(
        "prompt_injection",
        not matches,
        ["POL-10.3"],
        "instruction-like text found: " + ", ".join(matches) if matches
        else "",
    )


# ============================================================
# RUN ALL DETERMINISTIC CHECKS
# ============================================================

def run_all_checks(
    listing,
    other_listings=None,
):

    other_listings = other_listings or []

    return [
        check_required_fields(listing),

        check_title_length(listing),

        check_description_length(listing),

        check_price_format(listing),

        check_price_range(listing),

        check_category(listing),

        check_required_attributes(listing),

        check_condition(listing),

        check_tags(listing),

        check_contact_details(listing),

        check_exact_duplicate(
            listing,
            other_listings,
        ),

        check_near_duplicate(
            listing,
            other_listings,
        ),

        check_keyword_stuffing(listing),

        check_caps_and_symbols(listing),

        check_prompt_injection(listing),
    ]


# ============================================================
# COMPLETE REVIEW
# ============================================================

def review_listing(
    listing,
    other_listings=None,
):
    """
    Returns:

        checks
        failed
        model_triggers
    """

    checks = run_all_checks(
        listing,
        other_listings,
    )

    failed = [
        check
        for check in checks
        if not check["passed"]
        and not check["skipped"]
    ]

    return {
        "checks": checks,
        "failed": failed,
        "model_triggers": find_model_triggers(
            listing
        ),
    }


# ============================================================
# DEMO
# ============================================================

if __name__ == "__main__":

    good = {
        "title": (
            "Aurora 20000mAh Power Bank, "
            "22.5W Fast Charging, Black"
        ),

        "description": (
            "Portable power bank with two USB-C "
            "ports and one USB-A port. Charges a "
            "phone about four times. Includes a "
            "30 cm USB-C cable. Does not include "
            "a wall adapter."
        ),

        "category": "Electronics",

        "price": "49.99",

        "attributes": {
            "brand": "Aurora",
            "model": "PB-20",
            "condition": "New",
            "warranty": "12 months",
        },

        "seller": "Aurora Store",

        "tags": [
            "power bank",
            "charger",
        ],
    }

    bad = {
        "title": "BEST HEADPHONES!!!",

        "description": (
            "Call me 9876543210 for the lowest price."
        ),

        "category": "Gadgets",

        "price": "$49.999",

        "attributes": {
            "brand": "X",
            "condition": "Mint",
        },

        "seller": "Aurora Store",

        "tags": ["a"],
    }

    for name, listing in [
        ("GOOD", good),
        ("BAD", bad),
    ]:

        output = review_listing(
            listing,
            [good],
        )

        print(
            f"\n=== {name} LISTING ==="
        )

        print("\nFailed checks:")

        for check in output["failed"]:

            print(
                f"FAIL | "
                f"{check['check']:<22} | "
                f"{check['rules']} | "
                f"{check['message']}"
            )

        passed_count = sum(
            1
            for check in output["checks"]
            if check["passed"]
            and not check["skipped"]
        )

        skipped_count = sum(
            1
            for check in output["checks"]
            if check["skipped"]
        )

        print(
            f"\nPassed: {passed_count}"
            f" | Failed: {len(output['failed'])}"
            f" | Skipped: {skipped_count}"
            f" | Total: {len(output['checks'])}"
        )

        print(
            "\nModel triggers:"
        )

        for trigger in output["model_triggers"]:
            print(
                f"  {trigger['field']}: "
                f"{trigger['phrase']}"
            )
