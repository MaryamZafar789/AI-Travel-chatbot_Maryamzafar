"""
Structured entity extraction.

Fixes assessment section 2.3 (Faulty Information Extraction): the old code
only checked whether generic field-name words like "destination" appeared
in the message. This module extracts actual values -- real country names,
cities, nationalities, dates, passenger counts -- using alias dictionaries
and regex, so the system can reason about *what* was asked, not just
*that* a field-shaped word was present.

This is still a hand-built prototype extractor, not a trained NER model --
that limitation is intentional and documented in the README.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

# Canonical country name -> list of names/aliases/misspellings a customer
# might type. The canonical name must exactly match the "country" field
# used in knowledge_base.jsonl, since this is also used for strict
# destination filtering in rag.py (assessment section 2.1 / P0).
COUNTRY_ALIASES = {
    "United Arab Emirates": ["uae", "u.a.e", "emirates", "dubai", "abu dhabi", "sharjah", "united arab emirates"],
    "United Kingdom": ["uk", "u.k", "britain", "england", "london", "united kingdom"],
    "Turkey": ["turkey", "turkiye", "istanbul", "cappadocia", "turky"],
    "Thailand": ["thailand", "bangkok", "phuket", "thailnd"],
    "Malaysia": ["malaysia", "kuala lumpur", "genting", "kl", "malasyia", "malysia"],
    "Qatar": ["qatar", "doha", "qtar"],
    "Saudi Arabia": ["saudi", "saudi arabia", "ksa", "makkah", "mecca", "madinah", "medina", "jeddah", "riyadh", "umrah", "umra", "hajj"],
    "Azerbaijan": ["azerbaijan", "baku", "gabala", "azerbaijhan"],
    "Schengen Area": ["schengen", "europe", "eu visa", "france", "germany", "italy", "spain"],
}

# Nationality phrase -> implied country of origin (not destination). Used
# to fill the "nationality" slot separately from "destination".
NATIONALITY_ALIASES = {
    "Pakistani": ["pakistani", "pakistan", "pak national", "pak citizen"],
    "Indian": ["indian", "india"],
    "Bangladeshi": ["bangladeshi", "bangladesh"],
}

SERVICE_ALIASES = {
    "visa": ["visa", "visit visa", "immigration"],
    "ticketing": ["ticket", "flight", "fare", "baggage", "airline"],
    "tours": ["tour", "package", "holiday", "trip", "umrah", "honeymoon"],
    "insurance": ["insurance", "policy", "coverage", "bima"],
    "general": ["office", "timing", "contact", "payment", "hours"],
}

DATE_PATTERNS = [
    # "10 August", "10th August", "August 10"
    re.compile(r"\b(\d{1,2})(st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.I),
    re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(st|nd|rd|th)?\b", re.I),
    # "10/08/2026", "10-08-2026"
    re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b"),
]

PASSENGER_WORD_NUMS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "a": 1, "single": 1, "couple": 2,
}
PASSENGER_PATTERN = re.compile(
    r"\b(\d+|one|two|three|four|five|six|a|single|couple)\s*(adults?|passengers?|people|persons?|travell?ers?|kids?|childre?n?)\b",
    re.I,
)

CORRECTION_PATTERN = re.compile(
    r"\b(no+,?\s*(i (need|mean|want))|actually|i meant|not\s+\w+,?\s*(i need|but))\b", re.I
)


@dataclass
class ExtractedEntities:
    destination: Optional[str] = None
    nationality: Optional[str] = None
    service_category: Optional[str] = None
    travel_date: Optional[str] = None
    passenger_count: Optional[str] = None
    is_correction: bool = False


def _find_alias(text_lower: str, alias_map: dict) -> Optional[str]:
    # Sort candidate aliases by length (longest first) so "kuala lumpur"
    # matches before a shorter, coincidentally-contained alias would.
    best = None
    best_len = 0
    for canonical, aliases in alias_map.items():
        for alias in aliases:
            if alias in text_lower and len(alias) > best_len:
                best = canonical
                best_len = len(alias)
    return best


def extract_entities(message: str) -> ExtractedEntities:
    lower = message.lower()

    destination = _find_alias(lower, COUNTRY_ALIASES)
    nationality = _find_alias(lower, NATIONALITY_ALIASES)
    service_category = _find_alias(lower, SERVICE_ALIASES)

    travel_date = None
    for pattern in DATE_PATTERNS:
        m = pattern.search(message)
        if m:
            travel_date = m.group(0)
            break

    passenger_count = None
    m = PASSENGER_PATTERN.search(lower)
    if m:
        raw_num = m.group(1)
        num = PASSENGER_WORD_NUMS.get(raw_num, raw_num)
        passenger_count = f"{num} {m.group(2)}"

    is_correction = bool(CORRECTION_PATTERN.search(lower))

    return ExtractedEntities(
        destination=destination,
        nationality=nationality,
        service_category=service_category,
        travel_date=travel_date,
        passenger_count=passenger_count,
        is_correction=is_correction,
    )
