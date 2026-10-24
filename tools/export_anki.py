#!/usr/bin/env python3
"""Export every note's "Check yourself" questions as an Anki-importable TSV deck.

Usage:
    python3 tools/export_anki.py                       # all notes -> anki/all-notes.tsv
    python3 tools/export_anki.py --track <track-slug>  # only notes linked from that track's items
    python3 tools/export_anki.py --out path.tsv

Each line is: question <TAB> answer-side HTML <TAB> tags. Import in Anki with "Fields separated
by: Tab", "Allow HTML in fields" enabled, and the third field mapped to Tags. The answer side
names the note and the domain, and links to the note on GitHub, because the notes deliberately
leave the answers to the reader: say your answer out loud, then open the note to check.
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import sys

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
QUESTION_PATTERN = re.compile(r"^\d+\.\s+(.*\S)\s*$")


def load_data() -> dict:
    raw = (REPOSITORY_ROOT / "site" / "data.js").read_text(encoding="utf-8")
    return json.loads(raw[len("window.ROADMAP_DATA = "):].rstrip().rstrip(";"))


def questions_in(content: str) -> list[str]:
    lines = content.splitlines()
    start = next((index for index, line in enumerate(lines) if line.startswith("## Check yourself")), None)
    if start is None:
        return []
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    return [match.group(1) for line in lines[start:end] if (match := QUESTION_PATTERN.match(line))]


def inline_markdown_to_html(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    return escaped


def main(arguments: list[str]) -> int:
    data = load_data()
    track_slug = None
    output = None
    index = 0
    while index < len(arguments):
        if arguments[index] == "--track":
            track_slug = arguments[index + 1]
            index += 2
        elif arguments[index] == "--out":
            output = pathlib.Path(arguments[index + 1])
            index += 2
        else:
            print(f"unknown argument {arguments[index]}", file=sys.stderr)
            return 2

    note_paths_by_domain: dict[str, str] = {}
    allowed_notes: set[str] | None = None
    if track_slug:
        track = next((track for track in data.get("tracks", []) if track["slug"] == track_slug), None)
        if track is None:
            print(f"unknown track '{track_slug}'", file=sys.stderr)
            return 2
        keys = set(track["items"])
        allowed_notes = set()
        for domain in data["domains"]:
            stack = [item for section in domain["sections"] for item in section["items"]]
            while stack:
                item = stack.pop()
                stack.extend(item["children"])
                if f"{domain['slug']}:{item['id']}" in keys:
                    for link in item["links"]:
                        if link["kind"] == "note" and link.get("path"):
                            allowed_notes.add(link["path"])

    domain_titles = {domain["directory"]: domain["title"] for domain in data["domains"]}
    repository_url = data.get("repositoryUrl", "").rstrip("/")
    branch = data.get("branch", "main")
    lines = []
    for path, note in sorted(data["notes"].items()):
        if allowed_notes is not None and path not in allowed_notes:
            continue
        directory = path.split("/")[0]
        domain_title = domain_titles.get(directory, directory)
        link = f"{repository_url}/blob/{branch}/{path}" if repository_url else path
        tag = re.sub(r"[^a-z0-9]+", "-", domain_title.lower()).strip("-")
        for question in questions_in(note["content"]):
            front = inline_markdown_to_html(question)
            back = (f"<b>{html.escape(note['title'])}</b><br>{html.escape(domain_title)}<br>"
                    f"<a href=\"{html.escape(link)}\">{html.escape(path)}</a>")
            lines.append(f"{front}\t{back}\troadmap::{tag}")

    if output is None:
        output = REPOSITORY_ROOT / "anki" / (f"{track_slug}.tsv" if track_slug else "all-notes.tsv")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines)} cards to {output.relative_to(REPOSITORY_ROOT) if output.is_relative_to(REPOSITORY_ROOT) else output}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
