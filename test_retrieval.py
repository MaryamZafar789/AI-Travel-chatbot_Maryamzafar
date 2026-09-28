import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag import kb


def test_uae_visa_query_returns_only_uae():
    results = kb.retrieve("visa documents", category="visa", destination="United Arab Emirates")
    assert len(results) >= 1
    for chunk, _score in results:
        assert chunk.country == "United Arab Emirates"


def test_malaysia_visa_does_not_leak_turkey_or_uk():
    results = kb.retrieve("visa documents", category="visa", destination="Malaysia")
    countries = {c.country for c, _ in results}
    assert "Turkey" not in countries
    assert "United Kingdom" not in countries
    assert countries <= {"Malaysia"}


def test_qatar_visa_does_not_leak_other_countries():
    results = kb.retrieve("visa documents", category="visa", destination="Qatar")
    countries = {c.country for c, _ in results}
    assert countries <= {"Qatar"}


def test_umrah_package_does_not_return_thailand():
    results = kb.retrieve("umrah package", category="tours", destination="Saudi Arabia")
    for chunk, _score in results:
        assert chunk.country == "Saudi Arabia"
        assert "thailand" not in chunk.content.lower()


def test_unknown_destination_in_category_returns_empty_not_fallback():
    # No knowledge base entry exists for tours in "United Kingdom" as of
    # this dataset -- must return [] (unavailable), never substitute a
    # different country's chunk.
    results = kb.retrieve("tour package", category="tours", destination="United Kingdom")
    assert results == []


def test_category_only_filter_still_works_without_destination():
    results = kb.retrieve("visa documents", category="visa", top_k=5)
    assert len(results) >= 1
    for chunk, _score in results:
        assert chunk.category == "visa"


def test_top1_default():
    results = kb.retrieve("visa documents", category="visa", destination="United Arab Emirates")
    assert len(results) <= 1
