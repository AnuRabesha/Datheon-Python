import re
import json
import random
from pathlib import Path

INTENTS_FILE  = Path(__file__).parent / "intents.json"
PROJECT_ROOT  = Path(__file__).parent.resolve()
EXIT_COMMANDS = {"bye", "exit", "quit", "goodbye", "farewell"}
FALLBACK_THRESHOLD = 0  # minimum pattern matches to accept an intent

# ---------------------------------------------------------------------------
# State machine states
# ---------------------------------------------------------------------------
STATE_GREETING   = "greeting"
STATE_ACTIVE     = "active"
STATE_RESOLVED   = "resolved"
STATE_EXIT       = "exit"

# ---------------------------------------------------------------------------
# Security: path containment check (CWE-22 fix)
# ---------------------------------------------------------------------------
def _safe_path(path: Path, base: Path = PROJECT_ROOT) -> Path:
    """
    Resolve path and verify it stays within base.
    Raises ValueError on path traversal attempts.
    """
    resolved = path.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError(
            f"Access denied: '{resolved}' is outside the project directory."
        )
    return resolved


# ---------------------------------------------------------------------------
# Load & compile intents
# ---------------------------------------------------------------------------
def load_intents(path: Path) -> list[dict]:
    safe = _safe_path(path)                      # CWE-22: block path traversal
    if not safe.exists():
        raise FileNotFoundError(f"Intents file not found: '{safe}'")
    with open(safe, encoding="utf-8") as f:
        try:
            data = json.load(f)                  # raises json.JSONDecodeError on malformed JSON
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid intents JSON: {exc}") from exc
    if "intents" not in data or not isinstance(data["intents"], list):
        raise ValueError("Intents file must contain a top-level 'intents' list.")
    return data["intents"]


def compile_patterns(intents: list[dict]) -> list[dict]:
    """Pre-compile each pattern string into a regex for fast matching."""
    compiled = []
    for intent in intents:
        patterns = [re.compile(re.escape(p), re.IGNORECASE) for p in intent["patterns"]]
        compiled.append({
            "tag":       intent["tag"],
            "patterns":  patterns,
            "raw":       intent["patterns"],
            "responses": intent["responses"],
        })
    return compiled


# ---------------------------------------------------------------------------
# Input normalization
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)   # strip punctuation
    text = re.sub(r"\s+", " ", text)        # collapse whitespace
    return text


# ---------------------------------------------------------------------------
# Intent matching with confidence scoring
# ---------------------------------------------------------------------------
def score_intent(user_input: str, intent: dict) -> int:
    """
    Score = sum of word-counts of all patterns that match the input.
    Uses word-boundary anchors so 'there' won't match inside 'warranty'.
    Longer pattern matches are weighted higher (+1 per word in pattern).
    """
    score = 0
    for pattern, raw in zip(intent["patterns"], intent["raw"]):
        # Wrap the compiled pattern in word boundaries for whole-phrase matching
        bounded = re.compile(r"\b" + re.escape(raw) + r"\b", re.IGNORECASE)
        if bounded.search(user_input):
            score += len(raw.split())
    return score


def match_intent(user_input: str, intents: list[dict]) -> tuple[dict | None, int]:
    """Return the best-matching intent and its score."""
    best_intent, best_score = None, FALLBACK_THRESHOLD
    for intent in intents:
        score = score_intent(user_input, intent)
        if score > best_score:
            best_score  = score
            best_intent = intent
    return best_intent, best_score


# ---------------------------------------------------------------------------
# Fallback suggestions
# ---------------------------------------------------------------------------
FALLBACK_RESPONSES = [
    "I'm not sure I understood that. Could you rephrase?",
    "Hmm, I didn't quite catch that. Try asking about orders, shipping, returns, or hours.",
    "I don't have an answer for that yet. You can also reach a human agent at 1-800-TECH-SHOP.",
]

SUGGESTIONS = [
    "Here are some things I can help with:",
    "  - Business hours & location",
    "  - Order status & tracking",
    "  - Shipping & delivery",
    "  - Returns & refunds",
    "  - Warranty & technical support",
    "  - Payment methods & discounts",
    "  - Products & gift cards",
    "  Type 'agent' to speak with a human.",
]

def fallback_response(consecutive_misses: int) -> str:
    base = random.choice(FALLBACK_RESPONSES)
    if consecutive_misses >= 2:
        return base + "\n\n" + "\n".join(SUGGESTIONS)
    return base


# ---------------------------------------------------------------------------
# Conversation state machine
# ---------------------------------------------------------------------------
class ChatBot:
    def __init__(self):
        try:
            raw_intents = load_intents(INTENTS_FILE)
        except (FileNotFoundError, ValueError) as exc:
            raise RuntimeError(f"Failed to load intents: {exc}") from exc
        self.intents    = compile_patterns(raw_intents)
        self.state      = STATE_GREETING
        self.history: list[tuple[str, str]] = []
        self.misses     = 0
        self.turn       = 0

    def _pick_response(self, intent: dict) -> str:
        return random.choice(intent["responses"])

    def _log(self, user: str, bot: str) -> None:
        self.history.append((user, bot))

    def _is_exit(self, text: str) -> bool:
        return normalize(text) in EXIT_COMMANDS or any(
            re.search(rf"\b{cmd}\b", text, re.IGNORECASE) for cmd in EXIT_COMMANDS
        )

    def _handle_greeting_state(self, user_input: str) -> tuple[str, str]:
        """First turn: always greet, then try to resolve intent in same message."""
        greeting_intent = next(i for i in self.intents if i["tag"] == "greeting")
        greeting        = self._pick_response(greeting_intent)
        self.state      = STATE_ACTIVE

        # If the user already included a question in their greeting, resolve it
        intent, score = match_intent(user_input, self.intents)
        if intent and intent["tag"] not in ("greeting", "farewell"):
            return STATE_ACTIVE, greeting + "\n\n" + self._pick_response(intent)
        return STATE_ACTIVE, greeting

    def _handle_active_state(self, user_input: str) -> tuple[str, str]:
        """Main conversation loop: match intent and respond."""
        intent, score = match_intent(user_input, self.intents)

        if intent is None:
            self.misses += 1
            return STATE_ACTIVE, fallback_response(self.misses)

        self.misses = 0

        if intent["tag"] == "farewell":
            return STATE_EXIT, self._pick_response(intent)

        if intent["tag"] == "greeting" and self.turn > 1:
            # Re-greeting mid-conversation
            return STATE_ACTIVE, "Still here! What else can I help you with?"

        return STATE_ACTIVE, self._pick_response(intent)

    def respond(self, user_input: str) -> str:
        self.turn += 1
        raw = user_input.strip()

        if not raw:
            return "Please type a message — I'm here to help!"

        if self._is_exit(raw):
            self.state = STATE_EXIT
            farewell = next(i for i in self.intents if i["tag"] == "farewell")
            reply = self._pick_response(farewell)
            self._log(raw, reply)
            return reply

        normalized = normalize(raw)

        if self.state == STATE_GREETING and self.turn == 1:
            self.state, reply = self._handle_greeting_state(normalized)
        else:
            self.state, reply = self._handle_active_state(normalized)

        self._log(raw, reply)
        return reply

    @property
    def is_active(self) -> bool:
        return self.state != STATE_EXIT


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------
def print_banner() -> None:
    print("=" * 60)
    print("        TechShop Customer Support Bot")
    print("=" * 60)
    print("  Type your question and press Enter.")
    print("  Type 'bye', 'exit', or 'quit' to end the session.")
    print("=" * 60)


def run() -> None:
    print_banner()
    try:
        bot = ChatBot()
    except RuntimeError as exc:
        print(f"\n  Error: {exc}")
        print("  Please ensure 'intents.json' exists in the same directory.")
        return

    # Trigger the greeting on startup
    opening = bot.respond("hello")
    print(f"\n  Bot: {opening}\n")

    while bot.is_active:
        try:
            user_input = input("  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Bot: Session interrupted. Goodbye!")
            break

        if not user_input:
            continue

        reply = bot.respond(user_input)
        print(f"\n  Bot: {reply}\n")

        if not bot.is_active:
            break

    print("\n" + "=" * 60)
    print(f"  Session ended. Total turns: {bot.turn}")
    print("=" * 60)


if __name__ == "__main__":
    run()
