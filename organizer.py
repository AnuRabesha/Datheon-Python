import os
import json
import logging
import shutil
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Extension → category mapping
# ---------------------------------------------------------------------------
EXT_MAP = {
    # Documents
    ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents",
    ".xls": "Documents", ".xlsx": "Documents", ".ppt": "Documents",
    ".pptx": "Documents", ".txt": "Documents", ".csv": "Documents",
    ".odt": "Documents", ".rtf": "Documents",
    # Images
    ".jpg": "Images", ".jpeg": "Images", ".png": "Images",
    ".gif": "Images", ".bmp": "Images", ".svg": "Images",
    ".webp": "Images", ".tiff": "Images", ".ico": "Images",
    ".heic": "Images", ".raw": "Images",
    # Videos
    ".mp4": "Videos", ".mkv": "Videos", ".avi": "Videos",
    ".mov": "Videos", ".wmv": "Videos", ".flv": "Videos",
    ".webm": "Videos", ".m4v": "Videos",
    # Audio
    ".mp3": "Audio", ".wav": "Audio", ".flac": "Audio",
    ".aac": "Audio", ".ogg": "Audio", ".m4a": "Audio", ".wma": "Audio",
    # Archives
    ".zip": "Archives", ".rar": "Archives", ".7z": "Archives",
    ".tar": "Archives", ".gz": "Archives", ".bz2": "Archives",
    ".xz": "Archives", ".iso": "Archives",
    # Code
    ".py": "Code", ".js": "Code", ".ts": "Code", ".html": "Code",
    ".css": "Code", ".java": "Code", ".c": "Code", ".cpp": "Code",
    ".cs": "Code", ".go": "Code", ".rb": "Code", ".php": "Code",
    ".sh": "Code", ".bat": "Code", ".json": "Code", ".xml": "Code",
    ".yaml": "Code", ".yml": "Code", ".sql": "Code", ".rs": "Code",
    ".kt": "Code", ".swift": "Code", ".ipynb": "Code",
    # Executables
    ".exe": "Executables", ".msi": "Executables", ".dmg": "Executables",
    ".deb": "Executables", ".apk": "Executables",
    # Fonts
    ".ttf": "Fonts", ".otf": "Fonts", ".woff": "Fonts", ".woff2": "Fonts",
}

UNKNOWN_CATEGORY = "Misc"
LOG_DIR = Path(__file__).parent / "organizer_logs"


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
def setup_logger(log_path: Path) -> logging.Logger:
    """Configure a logger that writes to both console and a .log file."""
    LOG_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger("organizer")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


# ---------------------------------------------------------------------------
# Security: path containment check (fixes CWE-22)
# ---------------------------------------------------------------------------
def is_safe_path(base: Path, target: Path) -> bool:
    """Return True only if target resolves to a location inside base."""
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def safe_resolve(user_input: str, base: Path | None = None) -> Path | None:
    """
    Resolve a user-supplied path and optionally verify it stays within base.
    Returns None if the path escapes base (path traversal attempt).
    """
    resolved = Path(user_input).resolve()
    if base is not None and not is_safe_path(base, resolved):
        return None
    return resolved


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def resolve_collision(dest: Path) -> Path:
    """Append an incrementing counter if the destination already exists."""
    if not dest.exists():
        return dest
    stem, suffix, parent = dest.stem, dest.suffix, dest.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def save_json_log(session: dict, log_path: Path) -> None:
    """Persist the session dict as a JSON undo log."""
    with open(log_path.with_suffix(".json"), "w") as f:
        json.dump(session, f, indent=2)


def list_sessions() -> list[Path]:
    if not LOG_DIR.exists():
        return []
    return sorted(LOG_DIR.glob("session_*.json"), reverse=True)


def print_summary(session: dict, dry_run: bool, logger: logging.Logger) -> None:
    """Print and log the move breakdown and error list."""
    label = "Would move" if dry_run else "Files moved"
    logger.info("-" * 60)
    logger.info("Summary")
    logger.info(f"  {label:<14}: {len(session['moves'])}")
    logger.info(f"  {'Files skipped':<14}: {len(session['skipped'])}")
    logger.info(f"  {'Errors':<14}: {len(session['errors'])}")

    if session["moves"]:
        by_cat: dict[str, int] = {}
        for m in session["moves"]:
            by_cat[m["category"]] = by_cat.get(m["category"], 0) + 1
        logger.info("\n  Breakdown by category:")
        for cat, count in sorted(by_cat.items()):
            logger.info(f"    {cat:<20} {count:>4} file(s)")

    if session["errors"]:
        logger.warning("\n  Errors encountered:")
        for e in session["errors"]:
            logger.warning(f"    {e['file']}: {e['reason']}")


# ---------------------------------------------------------------------------
# Core: move a single file (extracted to fix large-function finding)
# ---------------------------------------------------------------------------
def move_file(src: Path, target: Path, category: str,
              session: dict, logger: logging.Logger) -> None:
    """
    Safely move src into target/category, enforcing path containment.
    Appends results to session dicts in-place.
    """
    dest_dir = target / category

    # CWE-22 fix: ensure dest_dir is inside target
    if not is_safe_path(target, dest_dir):
        logger.error(f"  [blocked]  {src.name}: destination escapes target directory")
        session["errors"].append({"file": src.name, "reason": "Path traversal blocked"})
        return

    try:
        dest_dir.mkdir(exist_ok=True)
    except PermissionError:
        logger.error(f"  [error]    {src.name}: permission denied creating {category}/")
        session["errors"].append({"file": src.name, "reason": "Permission denied creating folder"})
        return

    dest   = resolve_collision(dest_dir / src.name)
    status = "renamed" if dest.name != src.name else "moved"

    # CWE-22 fix: ensure final dest is inside target
    if not is_safe_path(target, dest):
        logger.error(f"  [blocked]  {src.name}: resolved destination escapes target")
        session["errors"].append({"file": src.name, "reason": "Path traversal blocked"})
        return

    try:
        shutil.move(str(src), str(dest))
        session["moves"].append({
            "src": str(src), "dest": str(dest),
            "src_name": src.name, "dest_name": dest.name,
            "category": category,
        })
        logger.info(f"  [{status:>7}]  {src.name:<40} -> {category}/")
    except PermissionError:
        logger.warning(f"  [skipped]  {src.name}: permission denied")
        session["errors"].append({"file": src.name, "reason": "Permission denied"})
        session["skipped"].append(src.name)
    except shutil.Error as exc:
        logger.warning(f"  [skipped]  {src.name}: {exc}")
        session["errors"].append({"file": src.name, "reason": str(exc)})
        session["skipped"].append(src.name)


# ---------------------------------------------------------------------------
# Core: organize
# ---------------------------------------------------------------------------
def organize(target_dir: str, dry_run: bool = False) -> dict:
    # CWE-22 fix: resolve and validate the user-supplied path
    target = safe_resolve(target_dir)
    if target is None or not target.is_dir():
        print(f"Error: '{target_dir}' is not a valid directory.")
        return {}

    ts       = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = LOG_DIR / f"session_{ts}.log"
    LOG_DIR.mkdir(exist_ok=True)
    logger   = setup_logger(log_file)

    mode = "[DRY RUN] " if dry_run else ""
    logger.info(f"\n{mode}Organizing : {target}")
    logger.info(f"Started at : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if dry_run:
        logger.info("  ** No files will be moved. Preview only. **")
    logger.info("-" * 60)

    session = {
        "target": str(target), "started_at": ts,
        "dry_run": dry_run, "moves": [], "skipped": [], "errors": [],
    }

    with os.scandir(target) as entries:
        files = sorted([e for e in entries if e.is_file()], key=lambda e: e.name)

    for entry in files:
        src      = Path(entry.path)
        category = EXT_MAP.get(src.suffix.lower(), UNKNOWN_CATEGORY)

        if dry_run:
            dest_dir = target / category
            dest     = resolve_collision(dest_dir / src.name)
            logger.info(f"  [preview]  {src.name:<40} -> {category}/")
            session["moves"].append({
                "src": str(src), "dest": str(dest),
                "src_name": src.name, "dest_name": dest.name,
                "category": category,
            })
        else:
            move_file(src, target, category, session, logger)

    print_summary(session, dry_run, logger)

    if not dry_run and session["moves"]:
        json_path = log_file.with_suffix(".json")
        save_json_log(session, log_file)
        logger.info(f"\n  Log saved  : {log_file}")
        logger.info(f"  Undo log   : {json_path}")

    logger.info(f"\nDone at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return session


# ---------------------------------------------------------------------------
# Undo helpers (extracted to fix large-function finding)
# ---------------------------------------------------------------------------
def _pick_session() -> Path | None:
    """Prompt the user to select a session from the log directory."""
    sessions = list_sessions()
    if not sessions:
        print("No sessions found to undo.")
        return None

    print("\nAvailable sessions:")
    for i, s in enumerate(sessions):
        with open(s) as f:
            data = json.load(f)
        flag = " [undone]" if "undone_at" in data else ""
        print(f"  {i + 1}. {data['started_at']}  |  "
              f"{len(data['moves'])} file(s)  |  {data['target']}{flag}")

    choice = input("\nEnter session number to undo (or Enter to cancel): ").strip()
    if not choice:
        return None
    try:
        return sessions[int(choice) - 1]
    except (ValueError, IndexError):
        print("Invalid choice.")
        return None


def _restore_moves(session: dict, target: Path) -> tuple[int, int]:
    """Restore all files from a session. Returns (restored, failed) counts."""
    restored = failed = 0
    for m in reversed(session["moves"]):
        src  = Path(m["dest"])
        dest = Path(m["src"])

        # CWE-22 fix: both src and dest must stay within target
        if not is_safe_path(target, src) or not is_safe_path(target, dest):
            print(f"  [blocked]  {src.name}: path escapes target — skipped")
            failed += 1
            continue

        if not src.exists():
            print(f"  [missing]  {src.name} — already moved or deleted")
            failed += 1
            continue

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            final = resolve_collision(dest)
            shutil.move(str(src), str(final))
            print(f"  [restored] {src.name:<40} -> {final.parent.name}/")
            restored += 1
        except (PermissionError, shutil.Error) as exc:
            print(f"  [error]    {src.name}: {exc}")
            failed += 1

    return restored, failed


# ---------------------------------------------------------------------------
# Core: undo
# ---------------------------------------------------------------------------
def undo(session_path: Path | None = None) -> None:
    if session_path is None:
        session_path = _pick_session()
    if session_path is None:
        return

    with open(session_path) as f:
        session = json.load(f)

    if session["dry_run"]:
        print("That session was a dry run — nothing to undo.")
        return

    # CWE-22 fix: validate the stored target path before using it
    target = safe_resolve(session["target"])
    if target is None or not target.is_dir():
        print(f"Error: session target '{session['target']}' is not accessible.")
        return

    print(f"\nUndoing session: {session['started_at']}")
    print(f"Target: {target}")
    print("-" * 60)

    restored, failed = _restore_moves(session, target)

    # Remove empty category folders
    for cat_dir in target.iterdir():
        if cat_dir.is_dir() and not any(cat_dir.iterdir()):
            cat_dir.rmdir()

    print("-" * 60)
    print(f"\n  Restored : {restored}")
    print(f"  Failed   : {failed}")

    session["undone_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(session_path, "w") as f:
        json.dump(session, f, indent=2)


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
def main_menu() -> None:
    default = str(Path.home() / "Downloads")

    while True:
        print("\n" + "=" * 50)
        print("         File Organizer")
        print("=" * 50)
        print("  1. Organize a directory")
        print("  2. Dry run  (preview only, no changes)")
        print("  3. Undo a session")
        print("  4. Exit")
        print("=" * 50)
        choice = input("Choose an option: ").strip()

        if choice in ("1", "2"):
            print(f"\nDefault: {default}")
            path = input("Directory path (Enter for default): ").strip() or default
            organize(path, dry_run=(choice == "2"))

        elif choice == "3":
            undo()

        elif choice == "4":
            print("Goodbye!")
            break

        else:
            print("Invalid option.")


if __name__ == "__main__":
    main_menu()
