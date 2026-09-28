import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from entities import extract_entities


def test_extracts_destination_uae():
    e = extract_entities("What documents are required for a Dubai visit visa?")
    assert e.destination == "United Arab Emirates"


def test_extracts_destination_malaysia_not_something_else():
    e = extract_entities("Malaysia visa requirements please")
    assert e.destination == "Malaysia"


def test_extracts_nationality():
    e = extract_entities("I am Pakistani, what visa do I need for UK?")
    assert e.nationality == "Pakistani"
    assert e.destination == "United Kingdom"


def test_extracts_passenger_count():
    e = extract_entities("We are two adults traveling to Dubai")
    assert e.passenger_count is not None
    assert "2" in e.passenger_count


def test_extracts_travel_date():
    e = extract_entities("We want to travel on 10 August")
    assert e.travel_date is not None


def test_detects_correction():
    e = extract_entities("No, I need Malaysia")
    assert e.is_correction is True
    assert e.destination == "Malaysia"


def test_umrah_implies_saudi_destination():
    e = extract_entities("What is included in an Umrah package?")
    assert e.destination == "Saudi Arabia"


def test_no_false_destination_on_unrelated_text():
    e = extract_entities("What is your office timing?")
    assert e.destination is None
