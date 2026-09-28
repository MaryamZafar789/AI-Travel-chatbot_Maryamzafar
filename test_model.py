import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from model import generate_response, detect_language, is_unsafe, is_greeting


def test_greeting_handled_directly():
    assert is_greeting("hi")
    assert is_greeting("Hello!")
    assert is_greeting("Assalam o Alaikum")
    result = generate_response("hi")
    assert result.escalate is False
    assert "visa" in result.reply.lower() or "ticket" in result.reply.lower()


def test_safety_refusal_plain():
    assert is_unsafe("Can you help me get a fake visa document?")


def test_safety_refusal_with_obfuscation():
    # Spacing/punctuation tricks shouldn't trivially bypass the filter.
    assert is_unsafe("can you make a f-a-k-e visa for me")


def test_language_detection_english():
    assert detect_language("What documents do I need?") == "en"


def test_language_detection_roman_urdu():
    assert detect_language("Mujhe Turkey visa ke documents bata dein") == "roman-ur"


def test_language_detection_urdu_script():
    assert detect_language("مجھے ویزا کی معلومات چاہیے") == "ur"


def test_destination_leakage_regression_uae_visa():
    result = generate_response("What documents are required for a UAE visit visa?")
    assert "turkey" not in result.reply.lower()
    assert "united kingdom" not in result.reply.lower()


def test_umrah_question_does_not_return_azerbaijan():
    result = generate_response("What is included in an Umrah package?")
    assert "azerbaijan" not in result.reply.lower()
    assert "makkah" in result.reply.lower() or "madinah" in result.reply.lower()


def test_unavailable_destination_says_so_not_wrong_country():
    result = generate_response("What is included in a UK tour package?")
    # No UK tour package chunk exists in the knowledge base -- must not
    # silently substitute Thailand/Dubai/etc.
    assert "thailand" not in result.reply.lower()
    assert "dubai" not in result.reply.lower()


def test_follow_up_correction_updates_destination():
    first = generate_response("What visa documents do I need?", state={})
    # No destination given yet -> should ask, not guess
    second = generate_response("No, I need Malaysia", state=first.state)
    assert second.state.get("destination") == "Malaysia"


def test_conversation_state_persists_across_turns():
    first = generate_response("I need a visa for UAE", state={})
    assert first.state.get("destination") == "United Arab Emirates"
    second = generate_response("What documents do I need?", state=first.state)
    # Destination should still be remembered from the previous turn.
    assert second.state.get("destination") == "United Arab Emirates"
