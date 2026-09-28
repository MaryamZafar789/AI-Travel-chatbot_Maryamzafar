"""
Local language model layer.

PROTOTYPE NOTE: this is a rule-based + template generator standing in for
a real fine-tuned local LLM. See README.md for the production upgrade path.

CHANGES from the technical assessment:
  - generate_response() now takes and returns a `state` dict (destination,
    nationality, service_category, travel_date, passenger_count). This is
    the conversation memory that was previously stored but unused
    (assessment 2.2: "Conversation history is stored but not used").
    Corrections like "No, I need Malaysia" now update `state.destination`
    and subsequent retrieval uses the corrected value (assessment: P1
    "Use conversation context").
  - Entities are extracted with entities.py instead of generic keyword
    presence checks (assessment 2.3).
  - Greetings are detected and answered directly instead of falling
    through to "no information found" (assessment 2.2).
  - retrieve() is now called with an explicit destination filter, so a
    known destination with no matching record returns an explicit
    "unavailable" message instead of a different country's data
    (assessment 2.1 / P0).
  - Safety keyword matching now normalizes punctuation/spacing so simple
    variants ("f a k e visa", "fake-visa") aren't trivially missed
    (assessment 2.6) -- still a keyword list, not true intent
    understanding, and that limitation is intentional and documented.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from entities import extract_entities
from rag import kb

CATEGORY_KEYWORDS = {
    "visa": ["visa", "vīza", "visa ka", "visa ke", "immigration", "embassy"],
    "ticketing": ["ticket", "flight", "fare", "baggage", "book", "seat", "ticket ki", "airline"],
    "tours": ["tour", "package", "holiday", "trip", "honeymoon", "family package", "umrah"],
    "insurance": ["insurance", "policy", "coverage", "claim", "bima"],
    "general": ["office", "timing", "contact", "payment", "hours", "whatsapp"],
}

SAFETY_TRIGGERS = [
    "fake document", "fake visa", "forged", "fraudulent", "illegal border",
    "smuggl", "bypass immigration", "fake bank statement", "backdated",
    "jaali", "jhoote documents", "counterfeit",
]

REQUIRED_SLOTS = {
    "visa": ["destination", "nationality", "travel_date"],
    "ticketing": ["destination", "travel_date"],
    "tours": ["destination", "passenger_count", "travel_date"],
    "insurance": ["destination", "travel_date"],
}
SLOT_LABELS = {
    "destination": "destination country",
    "nationality": "nationality",
    "travel_date": "travel date",
    "passenger_count": "number of travelers",
}

GREETING_PATTERN = re.compile(
    r"^\s*(hi|hii+|hello+|hey+|salam|assalam.?o.?alaikum|aoa|asalam.?o.?alikum)\b[\s!.,]*$", re.I
)

URDU_SCRIPT_RE = re.compile(r"[\u0600-\u06FF]")
ROMAN_URDU_HINTS = {"mujhe", "kya", "hai", "kar", "dain", "dein", "bata", "chahiye", "karna", "mein", "ke", "ka", "ki"}


@dataclass
class ChatResult:
    reply: str
    detected_language: str
    detected_category: Optional[str]
    used_chunks: list = field(default_factory=list)
    escalate: bool = False
    state: dict = field(default_factory=dict)


def detect_language(text: str, requested: str = "auto") -> str:
    if requested in ("en", "ur", "roman-ur"):
        return requested
    if URDU_SCRIPT_RE.search(text):
        return "ur"
    tokens = set(re.findall(r"[a-zA-Z']+", text.lower()))
    if tokens & ROMAN_URDU_HINTS:
        return "roman-ur"
    return "en"


def detect_category(text: str) -> Optional[str]:
    lower = text.lower()
    best, best_hits = None, 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lower)
        if hits > best_hits:
            best, best_hits = category, hits
    return best


def _normalize_for_safety_check(text: str) -> str:
    # Collapse spacing/punctuation tricks like "f a k e visa" or
    # "fake-visa" down to plain lowercase words, so the keyword list isn't
    # trivially bypassed by cosmetic obfuscation. Still not robust against
    # genuine paraphrasing -- that needs real language understanding.
    lower = text.lower()
    collapsed = re.sub(r"[\s\-_.]+", "", lower)
    return lower, collapsed


def is_unsafe(text: str) -> bool:
    lower, collapsed = _normalize_for_safety_check(text)
    for trigger in SAFETY_TRIGGERS:
        if trigger in lower:
            return True
        if trigger.replace(" ", "") in collapsed:
            return True
    return False


def is_greeting(text: str) -> bool:
    return bool(GREETING_PATTERN.match(text.strip()))


def _missing_slots(state: dict, category: str) -> list:
    missing = []
    for slot in REQUIRED_SLOTS.get(category, []):
        if not state.get(slot):
            missing.append(SLOT_LABELS[slot])
    return missing


GREETING_REPLIES = {
    "en": "Assalam-o-Alaikum! I can help with visas, tickets, tour packages, and travel insurance. What would you like to ask about?",
    "ur": "السلام علیکم! میں ویزا، ٹکٹنگ، ٹور پیکجز، اور سفری انشورنس میں مدد کر سکتا ہوں۔ آپ کیا جاننا چاہیں گے؟",
    "roman-ur": "Assalam-o-Alaikum! Main visa, ticketing, tour packages, aur travel insurance mein madad kar sakta hoon. Aap kya poochna chahenge?",
}

SAFETY_REPLIES = {
    "en": "I can't help with fake documents, illegal border crossing, or bypassing official requirements. If you have a genuine travel question, I'm happy to help — or I can connect you with a human consultant.",
    "ur": "میں جعلی دستاویزات، غیر قانونی سرحد عبور کرنے، یا سرکاری تقاضوں سے بچنے میں مدد نہیں کر سکتا۔ اگر آپ کا کوئی حقیقی سفری سوال ہے تو میں مدد کے لیے حاضر ہوں، یا آپ کو انسانی مشیر سے جوڑ سکتا ہوں۔",
    "roman-ur": "Main fake documents, illegal border crossing, ya official requirements bypass karne mein madad nahi kar sakta. Agar aap ka genuine travel se related sawal hai to zaroor madad karunga, ya aap ko human consultant se connect kar sakta hoon.",
}

NO_EVIDENCE_REPLIES = {
    "en": "I don't have verified information on that yet, so I don't want to guess. A travel consultant can confirm this for you — would you like me to share our contact/WhatsApp details?",
    "ur": "اس بارے میں میرے پاس تصدیق شدہ معلومات موجود نہیں، اس لیے میں اندازہ نہیں لگاؤں گا۔ ہمارا ٹریول کنسلٹنٹ اس کی تصدیق کر سکتا ہے — کیا آپ چاہیں گے میں رابطہ/واٹس ایپ کی تفصیلات دوں؟",
    "roman-ur": "Iss baare mein mere paas verified information nahi hai, is liye main andaza nahi lagaunga. Hamara travel consultant is ki tasdeeq kar sakta hai — kya aap chahenge main contact/WhatsApp details share karoon?",
}

DESTINATION_UNAVAILABLE_REPLIES = {
    "en": "I don't have verified {category} information for {destination} yet. I don't want to show you details for a different country by mistake. Would you like me to connect you with a consultant who can confirm this?",
    "ur": "میرے پاس {destination} کے لیے تصدیق شدہ {category} معلومات ابھی موجود نہیں۔ میں غلطی سے کسی اور ملک کی تفصیلات نہیں دکھانا چاہتا۔ کیا آپ چاہیں گے میں آپ کو مشیر سے جوڑ دوں؟",
    "roman-ur": "Mere paas {destination} ke liye verified {category} information abhi mojood nahi hai. Main ghalti se kisi aur mulk ki details nahi dikhana chahta. Kya aap chahenge main aap ko consultant se connect kar doon?",
}

CLARIFY_LEAD = {
    "en": "Happy to help. Could you also share your {slots}?",
    "ur": "خوشی سے مدد کروں گا۔ براہ کرم اپنی {slots} بھی بتائیں؟",
    "roman-ur": "Zaroor madad karunga. Please apni {slots} bhi share kar dein?",
}

DISCLAIMER = {
    "en": "\n\nNote: final confirmation is subject to verification by our consultant.",
    "ur": "\n\nنوٹ: حتمی تصدیق ہمارے مشیر کے ذریعے کی جائے گی۔",
    "roman-ur": "\n\nNote: final confirmation hamare consultant ke zariye ki jayegi.",
}

SOURCE_LINE = {
    "en": "(Verified: {date}, source: {source})",
    "ur": "(تصدیق شدہ: {date}, ماخذ: {source})",
    "roman-ur": "(Verified: {date}, source: {source})",
}


def _format_evidence_answer(chunks_with_scores, language: str) -> str:
    lines = []
    for chunk, _score in chunks_with_scores:
        source_note = SOURCE_LINE[language].format(date=chunk.last_checked, source=chunk.source_url)
        lines.append(f"- {chunk.content}\n  {source_note}")
    body = "\n".join(lines)
    lead = {
        "en": "Here's what I can confirm from our approved information:",
        "ur": "یہ وہ معلومات ہیں جن کی میں تصدیق کر سکتا ہوں:",
        "roman-ur": "Yeh hai jo main apni approved information se confirm kar sakta hoon:",
    }[language]
    return f"{lead}\n{body}{DISCLAIMER[language]}"


def generate_response(message: str, state: Optional[dict] = None, requested_language: str = "auto") -> ChatResult:
    state = dict(state or {})
    language = detect_language(message, requested_language)

    if is_greeting(message):
        return ChatResult(
            reply=GREETING_REPLIES[language],
            detected_language=language,
            detected_category=None,
            state=state,
        )

    if is_unsafe(message):
        return ChatResult(
            reply=SAFETY_REPLIES[language],
            detected_language=language,
            detected_category=None,
            escalate=True,
            state=state,
        )

    # --- Extract entities and update conversation memory -----------------
    entities = extract_entities(message)
    category = entities.service_category or detect_category(message)

    if entities.destination:
        # A correction ("No, I need Malaysia") or a fresh mention both
        # simply overwrite the stored destination -- either way the
        # customer just told us the destination to use going forward.
        state["destination"] = entities.destination
    if entities.nationality:
        state["nationality"] = entities.nationality
    if entities.travel_date:
        state["travel_date"] = entities.travel_date
    if entities.passenger_count:
        state["passenger_count"] = entities.passenger_count
    if category:
        state["service_category"] = category
    else:
        category = state.get("service_category")

    destination = state.get("destination")

    # --- Retrieval: category first, then STRICT destination match --------
    results = kb.retrieve(message, category=category, destination=destination, top_k=1)

    if not results:
        if destination and category:
            # We know exactly what they want and we know it's not in the
            # knowledge base for that destination -- say so explicitly
            # rather than silently falling back to unrelated content.
            reply = DESTINATION_UNAVAILABLE_REPLIES[language].format(category=category, destination=destination)
        else:
            reply = NO_EVIDENCE_REPLIES[language]
        return ChatResult(
            reply=reply,
            detected_language=language,
            detected_category=category,
            escalate=True,
            state=state,
        )

    missing = _missing_slots(state, category) if category else []
    reply = _format_evidence_answer(results, language)

    if missing:
        clarify = CLARIFY_LEAD[language].format(slots=", ".join(missing))
        reply = f"{reply}\n\n{clarify}"

    return ChatResult(
        reply=reply,
        detected_language=language,
        detected_category=category,
        used_chunks=[c.chunk_id for c, _ in results],
        escalate=False,
        state=state,
    )
