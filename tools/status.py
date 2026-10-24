#!/usr/bin/env python3
"""Print the build status: items, notes, coverage, and per-track coverage.

Usage: python3 tools/status.py [--markdown]
Reads site/data.js (run tools/build.py first).
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_data() -> dict:
    raw = (REPOSITORY_ROOT / "site" / "data.js").read_text(encoding="utf-8")
    return json.loads(raw[len("window.ROADMAP_DATA = "):].rstrip().rstrip(";"))


def walk(items: list[dict]):
    for item in items:
        yield item
        yield from walk(item["children"])


def has_note(item: dict) -> bool:
    return any(link["kind"] == "note" and link.get("path") for link in item["links"])


def main(arguments: list[str]) -> int:
    data = load_data()
    markdown = "--markdown" in arguments
    rows = []
    total_items = total_with_note = 0
    for domain in data["domains"]:
        items = [item for section in domain["sections"] for item in walk(section["items"])]
        with_note = sum(1 for item in items if has_note(item))
        total_items += len(items)
        total_with_note += with_note
        rows.append((domain["directory"], len(items), with_note, domain["noteCount"]))
    words = sum(len(note["content"].split()) for note in data["notes"].values())
    try:
        commits = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        commits = "?"

    separator = " | " if markdown else "  "
    header = ["domain", "items", "items with note", "notes"]
    if markdown:
        print("| " + " | ".join(header) + " |")
        print("|---|---:|---:|---:|")
    else:
        print(f"{header[0]:<30}{separator}{header[1]:>5}{separator}{header[2]:>15}{separator}{header[3]:>5}")
    for directory, count, with_note, notes in rows:
        if markdown:
            print(f"| {directory} | {count} | {with_note} | {notes} |")
        else:
            print(f"{directory:<30}{separator}{count:>5}{separator}{with_note:>15}{separator}{notes:>5}")
    percent = total_with_note * 100 // total_items if total_items else 0
    print()
    print(f"Items: {total_items}. Items with a note: {total_with_note} ({percent}%). Notes: {len(data['notes'])} ({words:,} words). Commits: {commits}.")
    for track in data.get("tracks", []):
        keys = set(track["items"])
        covered = 0
        for domain in data["domains"]:
            for section in domain["sections"]:
                for item in walk(section["items"]):
                    if f"{domain['slug']}:{item['id']}" in keys and has_note(item):
                        covered += 1
        track_percent = covered * 100 // len(keys) if keys else 0
        print(f"Track '{track['title']}': {len(keys)} items, {covered} with a note ({track_percent}%).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
