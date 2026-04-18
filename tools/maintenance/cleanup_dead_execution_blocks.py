import re
import shutil
from pathlib import Path

TARGET_FILE = Path(__file__).resolve().parents[2] / "AINDY" / "routes" / "memory_router.py"
BACKUP_FILE = TARGET_FILE.with_suffix(".py.bak")


def backup_file():
    shutil.copy(TARGET_FILE, BACKUP_FILE)
    print(f"[backup] Created: {BACKUP_FILE}")


def is_decorator(line):
    return line.strip().startswith("@router")


def is_def(line):
    return re.match(r"\s*def\s+", line) or re.match(r"\s*async\s+def\s+", line)


def is_new_block(line):
    return is_decorator(line) or is_def(line)


def cleanup_dead_blocks():
    lines = TARGET_FILE.read_text(encoding="utf-8").splitlines()
    cleaned = []

    i = 0
    while i < len(lines):
        line = lines[i]
        cleaned.append(line)

        # Detect pipeline return
        if "return await _execute_memory" in line:
            i += 1

            # Skip dead code until next function/decorator
            while i < len(lines):
                next_line = lines[i]

                if is_new_block(next_line):
                    break

                # Skip (delete) dead lines
                i += 1

            continue

        i += 1

    TARGET_FILE.write_text("\n".join(cleaned) + "\n", encoding="utf-8")
    print("[cleanup] Dead execution blocks removed.")


def main():
    if not TARGET_FILE.exists():
        print(f"[error] File not found: {TARGET_FILE}")
        return

    backup_file()
    cleanup_dead_blocks()


if __name__ == "__main__":
    main()
