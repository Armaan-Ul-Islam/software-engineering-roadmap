#!/usr/bin/env python3
"""Link notes into their roadmap items.

Every note ends with a footer such as:

    Part of [Databases](../README.md) · items 5.2, 5.3

This script reads that footer for every note, finds the matching checklist items in the
domain README, and inserts `[notes](notes/<file>.md)` as the first link of each item line
when it is not already there. It is idempotent and reports footers it cannot match.

Usage: python3 tools/link_notes.py [--check] [domain-folder ...]
"""

from __future__ import annotations

import pathlib
import re
import sys

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
DOMAIN_DIRECTORY_PATTERN = re.compile(r"^\d{2}-[a-z0-9-]+$")
FOOTER_PATTERN = re.compile(r"^Part of \[[^\]]+\]\((?:\.\./)+README\.md\)\s*·\s*items?\s+([0-9.,\s]+)$", re.MULTILINE)
ITEM_LINE_PATTERN = re.compile(r"^(\s*- \[[ xX]\] )(\d+(?:\.\d+)*)(\s+)(.*?)\s*$")


def footer_items(note_text: str) -> list[str]:
    match = FOOTER_PATTERN.search(note_text)
    if not match:
        return []
    return [item.strip() for item in match.group(1).split(",") if item.strip()]


def insert_note_link(line: str, relative_note_path: str) -> str:
    match = ITEM_LINE_PATTERN.match(line)
    if not match:
        return line
    prefix, item_id, spacing, rest = match.groups()
    if f"]({relative_note_path})" in rest:
        return line
    note_link = f"[notes]({relative_note_path})"
    first_link_index = rest.find(" · [")
    if first_link_index == -1:
        new_rest = f"{rest} · {note_link}"
    else:
        new_rest = f"{rest[:first_link_index]} · {note_link}{rest[first_link_index:]}"
    return f"{prefix}{item_id}{spacing}{new_rest}"


def process_domain(domain_directory: pathlib.Path, check_only: bool) -> tuple[int, list[str]]:
    readme = domain_directory / "README.md"
    lines = readme.read_text(encoding="utf-8").splitlines()
    problems: list[str] = []
    changed = 0

    for note_file in sorted(domain_directory.rglob("*.md")):
        if note_file == readme:
            continue
        items = footer_items(note_file.read_text(encoding="utf-8"))
        relative_note_path = note_file.relative_to(domain_directory).as_posix()
        if not items:
            problems.append(f"{note_file.relative_to(REPOSITORY_ROOT).as_posix()}: no 'Part of [...](../README.md) · item N.N' footer")
            continue
        for item_id in items:
            matched = False
            for index, line in enumerate(lines):
                match = ITEM_LINE_PATTERN.match(line)
                if match and match.group(2) == item_id:
                    matched = True
                    new_line = insert_note_link(line, relative_note_path)
                    if new_line != line:
                        lines[index] = new_line
                        changed += 1
                    break
            if not matched:
                problems.append(f"{note_file.relative_to(REPOSITORY_ROOT).as_posix()}: item {item_id} not found in {readme.relative_to(REPOSITORY_ROOT).as_posix()}")

    if changed and not check_only:
        readme.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed, problems


def main(arguments: list[str]) -> int:
    check_only = "--check" in arguments
    selected = {argument.strip("/") for argument in arguments if not argument.startswith("--")}
    total_changed = 0
    all_problems: list[str] = []
    for domain_directory in sorted(REPOSITORY_ROOT.iterdir()):
        if not (domain_directory.is_dir() and DOMAIN_DIRECTORY_PATTERN.match(domain_directory.name)):
            continue
        if selected and domain_directory.name not in selected:
            continue
        changed, problems = process_domain(domain_directory, check_only)
        total_changed += changed
        all_problems.extend(problems)
        if changed:
            print(f"{domain_directory.name}/README.md: {changed} item line(s) {'would be ' if check_only else ''}updated")
    for problem in all_problems:
        print(f"warning: {problem}")
    print(f"{total_changed} link(s) {'to add' if check_only else 'added'}, {len(all_problems)} warning(s).")
    return 1 if all_problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
