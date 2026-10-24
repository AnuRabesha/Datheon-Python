import os
import random
from pathlib import Path

# ---------------------------------------------------------------------------
# Word list — safe load with clear error on missing file
# ---------------------------------------------------------------------------
WORD_FILE = Path(__file__).parent / "google-10000-english-no-swears.txt"

def _load_words() -> list[str]:
    if not WORD_FILE.exists():
        raise FileNotFoundError(
            f"Word list not found: '{WORD_FILE}'\n"
            "Download it from: https://raw.githubusercontent.com/"
            "first20hours/google-10000-english/master/"
            "google-10000-english-no-swears.txt"
        )
    with open(WORD_FILE, encoding="utf-8") as f:
        return [w.strip() for w in f if w.strip().isalpha()]

# ---------------------------------------------------------------------------
# Difficulty config
# ---------------------------------------------------------------------------
DIFFICULTY = {
    "easy":   {"min": 4, "max": 5,  "attempts": 8},
    "medium": {"min": 6, "max": 8,  "attempts": 6},
    "hard":   {"min": 9, "max": 15, "attempts": 5},
}

# ---------------------------------------------------------------------------
# ASCII gallows — 7 progressive stages (0 = empty, 6 = full)
# ---------------------------------------------------------------------------
STAGES = [
    """
       -----
       |   |
           |
           |
           |
           |
    =========""",
    """
       -----
       |   |
       O   |
           |
           |
           |
    =========""",
    """
       -----
       |   |
       O   |
       |   |
           |
           |
    =========""",
    """
       -----
       |   |
       O   |
      /|   |
           |
           |
    =========""",
    """
       -----
       |   |
       O   |
      /|\\  |
           |
           |
    =========""",
    """
       -----
       |   |
       O   |
      /|\\  |
      /    |
           |
    =========""",
    """
       -----
       |   |
       O   |
      /|\\  |
      / \\  |
           |
    ========="""
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def get_stage(mistakes: int, max_attempts: int) -> str:
    """Map mistakes linearly to one of 7 stages (0–6)."""
    index = min(round(mistakes / max_attempts * 6), 6)
    return STAGES[index]


def masked(word: str, guessed: set) -> str:
    return " ".join(c.upper() if c in guessed else "_" for c in word)


def choose_difficulty() -> str:
    while True:
        choice = input("Choose difficulty (easy / medium / hard): ").lower().strip()
        if choice in DIFFICULTY:
            return choice
        print("  Invalid choice. Please enter easy, medium, or hard.")


# ---------------------------------------------------------------------------
# Victory / defeat screens
# ---------------------------------------------------------------------------
def victory_screen(word: str, mistakes: int, max_attempts: int) -> None:
    clear()
    print("""
       -----
       |   |
           |
           |
           |
           |
    =========""")
    print()
    print("  *" * 20)
    print()
    print("        YOU WON!")
    print()
    print(f"        The word was: {word.upper()}")
    print(f"        Wrong guesses: {mistakes} / {max_attempts}")
    print()
    print("  *" * 20)
    print()


def defeat_screen(word: str) -> None:
    clear()
    print(STAGES[6])
    print()
    print("  #" * 20)
    print()
    print("        GAME OVER!")
    print()
    print(f"        The word was: {word.upper()}")
    print()
    print("  #" * 20)
    print()


# ---------------------------------------------------------------------------
# Core game loop
# ---------------------------------------------------------------------------
def hangman(all_words: list[str]) -> bool:
    clear()
    print("=" * 42)
    print("          Welcome to Hangman!")
    print("=" * 42)
    print()

    level        = choose_difficulty()
    cfg          = DIFFICULTY[level]
    max_attempts = cfg["attempts"]

    pool = [w for w in all_words if cfg["min"] <= len(w) <= cfg["max"]]
    word = random.choice(pool)

    guessed  = set()
    mistakes = 0

    while mistakes < max_attempts:
        clear()
        print(get_stage(mistakes, max_attempts))
        print()
        print(f"  [{level.upper()}]  {masked(word, guessed)}")
        print()
        print(f"  Attempts left : {max_attempts - mistakes}")

        if guessed:
            print(f"  Guessed       : {', '.join(sorted(guessed)).upper()}")

        print()

        # Win check
        if all(c in guessed for c in word):
            victory_screen(word, mistakes, max_attempts)
            return True

        # Input
        try:
            guess = input("  Guess a letter: ").lower().strip()
        except EOFError:
            break

        if len(guess) != 1 or not guess.isalpha():
            print("  Please enter a single letter.")
            input("  Press Enter to continue...")
            continue

        if guess in guessed:
            print("  You already guessed that letter!")
            input("  Press Enter to continue...")
            continue

        guessed.add(guess)

        if guess not in word:
            mistakes += 1
            remaining = max_attempts - mistakes
            if remaining > 0:
                print(f"  Wrong! {remaining} attempt(s) left.")
                input("  Press Enter to continue...")

    # Final win check (catches win on last guess)
    if all(c in guessed for c in word):
        victory_screen(word, mistakes, max_attempts)
        return True

    defeat_screen(word)
    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    try:
        all_words = _load_words()
    except FileNotFoundError as exc:
        print(f"\nError: {exc}")
        return

    try:
        while True:
            hangman(all_words)
            again = input("  Play again? (yes / no): ").lower().strip()
            if again not in ("yes", "y"):
                clear()
                print("\n  Thanks for playing Hangman. Goodbye!\n")
                break
    except KeyboardInterrupt:
        print("\n\n  Game interrupted. Goodbye!")


if __name__ == "__main__":
    main()
