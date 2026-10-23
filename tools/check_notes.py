#!/usr/bin/env python3
"""Check that every note follows the note conventions.

Usage:
    python3 tools/check_notes.py            # check all notes
    python3 tools/check_notes.py 05-java    # check notes under a folder

Errors (exit code 1): missing or misordered required sections, missing footer, wildcard
imports in code, fewer than three "Check yourself" questions, fewer than two "Go deeper" links.
Warnings: word count outside 450-2300, em dashes, code fences without a language, loop or
catch variables that are single letters.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
DOMAIN_DIRECTORY_PATTERN = re.compile(r"^\d{2}-[a-z0-9-]+$")
REQUIRED_HEADINGS = ["## The idea", "## Example", "## Pitfalls", "## Check yourself", "## Go deeper"]
FOOTER_PATTERN = re.compile(r"^Part of \[[^\]]+\]\((?:\.\./)+README\.md\) · items? \d+(?:\.\d+)*(?:, \d+(?:\.\d+)*)*$")
LINK_PATTERN = re.compile(r"\[[^\]]+\]\([^)]+\)")
SINGLE_LETTER_PATTERN = re.compile(r"(for \((?:int|var|long) [a-z] =)|(catch \(\w+ [a-z]\))|(\([A-Za-z<>\[\]]+ [a-z]\) ->)|(\b[a-z] -> )")


def note_files(paths: list[pathlib.Path]) -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
            continue
        for markdown_file in sorted(path.rglob("*.md")):
            relative = markdown_file.relative_to(REPOSITORY_ROOT)
            if len(relative.parts) < 2 or not DOMAIN_DIRECTORY_PATTERN.match(relative.parts[0]):
                continue
            if markdown_file.name == "README.md" and len(relative.parts) == 2:
                continue
            files.append(markdown_file)
    return files


def check_note(path: pathlib.Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    non_empty = [line for line in lines if line.strip()]

    if not lines or not lines[0].startswith("# "):
        errors.append("first line must be '# Title'")
    if not any(line.startswith("> **In one sentence:**") for line in lines):
        errors.append("missing '> **In one sentence:**' line")
    if "**Why it matters:**" not in text:
        errors.append("missing '**Why it matters:**' paragraph")

    heading_positions = []
    for required in REQUIRED_HEADINGS:
        position = next((index for index, line in enumerate(lines) if line == required or line.startswith(required + ":") or line.startswith(required + " ")), None)
        if position is None:
            errors.append(f"missing section '{required}'")
        heading_positions.append(position)
    present_positions = [position for position in heading_positions if position is not None]
    if present_positions != sorted(present_positions):
        errors.append("sections are out of order")

    if not non_empty or not FOOTER_PATTERN.match(non_empty[-1].strip()):
        errors.append("last line must be the footer 'Part of [Title](../README.md) · items N.N'")

    check_yourself_index = next((index for index, line in enumerate(lines) if line.startswith("## Check yourself")), None)
    go_deeper_index = next((index for index, line in enumerate(lines) if line.startswith("## Go deeper")), None)
    if check_yourself_index is not None and go_deeper_index is not None:
        questions = [line for line in lines[check_yourself_index:go_deeper_index] if re.match(r"^\d+\. ", line)]
        if len(questions) < 3:
            errors.append(f"'Check yourself' has {len(questions)} numbered questions; need at least 3")
        go_deeper_text = "\n".join(lines[go_deeper_index:])
        if len(LINK_PATTERN.findall(go_deeper_text)) < 2:
            errors.append("'Go deeper' needs at least two links")

    in_code = False
    code_lines: list[str] = []
    for line in lines:
        if line.startswith("```"):
            if not in_code and line.strip() == "```":
                warnings.append("code fence without a language tag")
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
    code_text = "\n".join(code_lines)
    if re.search(r"^import .*\.\*;", code_text, re.MULTILINE):
        errors.append("wildcard import in a code block")
    if SINGLE_LETTER_PATTERN.search(code_text):
        warnings.append("single-letter variable in a loop, catch or lambda")

    word_count = len(re.findall(r"\b\w+\b", text))
    if word_count < 450 or word_count > 2300:
        warnings.append(f"word count {word_count} is outside 450-2300")
    if "—" in text:
        warnings.append("contains an em dash")

    return errors, warnings


def main(arguments: list[str]) -> int:
    paths = [(REPOSITORY_ROOT / argument).resolve() for argument in arguments] or [REPOSITORY_ROOT]
    total_errors = 0
    total_warnings = 0
    files = note_files(paths)
    for path in files:
        errors, warnings = check_note(path)
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        for error in errors:
            print(f"error: {relative}: {error}")
        for warning in warnings:
            print(f"warning: {relative}: {warning}")
        total_errors += len(errors)
        total_warnings += len(warnings)
    print(f"{len(files)} notes checked, {total_errors} error(s), {total_warnings} warning(s).")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
