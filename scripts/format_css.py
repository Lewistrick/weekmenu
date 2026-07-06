"""Normalize CSS formatting by removing blank lines inside rule blocks."""

from __future__ import annotations

import sys
from pathlib import Path


def _should_insert_rule_break(output: list[str]) -> bool:
    """Return whether a blank line should separate the next rule."""
    if not output or output[-1] == "":
        return False
    return output[-1] == "}"


def format_css(text: str) -> str:
    """Collapse intra-rule blank lines while keeping blank lines between rules."""
    lines = text.splitlines()
    output: list[str] = []
    in_block = False
    pending_blank = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if not in_block:
                pending_blank = True
            continue

        if stripped.endswith("{"):
            if pending_blank and _should_insert_rule_break(output):
                output.append("")
            pending_blank = False
            output.append(stripped)
            in_block = True
            continue

        if stripped == "}":
            output.append(stripped)
            in_block = False
            pending_blank = True
            continue

        if pending_blank and _should_insert_rule_break(output):
            output.append("")
        pending_blank = False
        output.append(stripped)

    return "\n".join(output).rstrip() + "\n"


def main(argv: list[str]) -> int:
    """Format one or more CSS files in place."""
    if len(argv) < 2:
        print("Usage: format_css.py <file.css> [...]", file=sys.stderr)
        return 1

    exit_code = 0
    for arg in argv[1:]:
        path = Path(arg)
        original = path.read_text(encoding="utf-8")
        formatted = format_css(original)
        if formatted != original:
            path.write_text(formatted, encoding="utf-8")
            print(f"Formatted {path}")
        else:
            print(f"Already formatted {path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
