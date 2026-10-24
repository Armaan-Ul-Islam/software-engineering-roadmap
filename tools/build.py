#!/usr/bin/env python3
"""Build site/data.js from the domain roadmaps and notes.

Usage:
    python3 tools/build.py          # validate and write site/data.js
    python3 tools/build.py --check  # validate only

The script reads every `NN-<slug>/README.md`, parses the `## Roadmap` checklist into
sections and items, embeds every other markdown file in the domain folder as a note, and
validates local links and item IDs. It fails (exit code 1) on broken local links, duplicate
IDs, or structural problems, so it doubles as the repository's consistency check.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import sys
from urllib.parse import urlparse

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTPUT_FILE = REPOSITORY_ROOT / "site" / "data.js"
REPOSITORY_URL = "https://github.com/Armaan-Ul-Islam/software-engineering-roadmap"
DEFAULT_BRANCH = "main"

DOMAIN_DIRECTORY_PATTERN = re.compile(r"^(\d{2})-([a-z0-9-]+)$")
SECTION_PATTERN = re.compile(r"^### (\d+)\.\s+(.+?)\s*$")
ITEM_PATTERN = re.compile(r"^(\s*)- \[([ xX])\] (\d+(?:\.\d+)*)\s+(.*?)\s*$")
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
PREREQUISITE_LINK_PATTERN = re.compile(r"\.\./(\d{2})-([a-z0-9-]+)/README\.md")
SEPARATOR_PATTERN = re.compile(r"(\s*·\s*)+")


class BuildError(Exception):
    pass


def link_kind(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        host = urlparse(url).netloc.lower()
        path = urlparse(url).path.lower()
        if "youtube.com" in host or "youtu.be" in host:
            return "video"
        if path.endswith(".pdf"):
            return "pdf"
        if host == "github.com" or host.endswith(".github.io"):
            return "repo"
        return "article"
    if url.endswith(".md") or ".md#" in url:
        return "note"
    return "file"


def normalise_local_target(source_file: pathlib.Path, url: str) -> pathlib.Path:
    target_without_fragment = url.split("#", 1)[0]
    return (source_file.parent / target_without_fragment).resolve()


def relative_to_root(path: pathlib.Path) -> str:
    return path.relative_to(REPOSITORY_ROOT).as_posix()


def extract_links(source_file: pathlib.Path, text: str, errors: list[str], line_number: int) -> list[dict]:
    links = []
    for label, url in LINK_PATTERN.findall(text):
        kind = link_kind(url)
        link = {"label": label.strip(), "url": url, "kind": kind}
        if kind in ("note", "file"):
            target = normalise_local_target(source_file, url)
            if not target.exists():
                errors.append(f"{relative_to_root(source_file)}:{line_number}: broken local link '{url}'")
            else:
                link["path"] = relative_to_root(target)
        links.append(link)
    return links


def strip_links(text: str) -> str:
    without_links = LINK_PATTERN.sub("", text)
    without_separators = SEPARATOR_PATTERN.sub(" ", without_links)
    return re.sub(r"\s+", " ", without_separators).strip(" -—·")


def parse_readme(domain_directory: pathlib.Path, errors: list[str]) -> dict:
    readme = domain_directory / "README.md"
    lines = readme.read_text(encoding="utf-8").splitlines()
    match = DOMAIN_DIRECTORY_PATTERN.match(domain_directory.name)
    order, slug = int(match.group(1)), match.group(2)

    title = None
    summary_lines: list[str] = []
    prerequisites: list[str] = []
    abilities: list[str] = []
    sections: list[dict] = []
    seen_ids: set[str] = set()
    in_roadmap = False
    in_abilities = False
    item_stack: list[tuple[int, dict]] = []

    for line_number, line in enumerate(lines, 1):
        if title is None:
            if line.startswith("# "):
                title = line[2:].strip()
            continue
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            in_roadmap = heading == "roadmap"
            in_abilities = False
            item_stack = []
            continue
        if not in_roadmap:
            if line.startswith("> ") and not sections and not prerequisites:
                summary_lines.append(line[2:].strip())
            elif line.startswith("**Prerequisites:**"):
                for _, prerequisite_slug in PREREQUISITE_LINK_PATTERN.findall(line):
                    prerequisites.append(prerequisite_slug)
                for label, url in LINK_PATTERN.findall(line):
                    target = normalise_local_target(readme, url)
                    if not target.exists():
                        errors.append(f"{relative_to_root(readme)}:{line_number}: broken prerequisite link '{url}'")
            elif line.startswith("**Done when you can:**"):
                in_abilities = True
            elif in_abilities:
                if line.startswith("- "):
                    abilities.append(line[2:].strip())
                elif line.strip() == "":
                    continue
                else:
                    in_abilities = False
            continue

        section_match = SECTION_PATTERN.match(line)
        if section_match:
            section_id = section_match.group(1)
            if section_id in seen_ids:
                errors.append(f"{relative_to_root(readme)}:{line_number}: duplicate section id {section_id}")
            seen_ids.add(section_id)
            sections.append({"id": section_id, "title": section_match.group(2), "items": []})
            item_stack = []
            continue

        item_match = ITEM_PATTERN.match(line)
        if item_match:
            if not sections:
                errors.append(f"{relative_to_root(readme)}:{line_number}: checklist item before any '### N. Title' section")
                continue
            indent, done_mark, item_id, rest = item_match.groups()
            level = len(indent.replace("\t", "  ")) // 2
            if item_id in seen_ids:
                errors.append(f"{relative_to_root(readme)}:{line_number}: duplicate item id {item_id}")
            seen_ids.add(item_id)
            expected_prefix = sections[-1]["id"] + "."
            if not item_id.startswith(expected_prefix):
                errors.append(f"{relative_to_root(readme)}:{line_number}: item id {item_id} does not belong to section {sections[-1]['id']}")
            item = {
                "id": item_id,
                "text": strip_links(rest),
                "done": done_mark.lower() == "x",
                "links": extract_links(readme, rest, errors, line_number),
                "children": [],
            }
            if not item["text"]:
                errors.append(f"{relative_to_root(readme)}:{line_number}: item {item_id} has no text")
            while item_stack and item_stack[-1][0] >= level:
                item_stack.pop()
            if level == 0 or not item_stack:
                sections[-1]["items"].append(item)
            else:
                parent = item_stack[-1][1]
                if not item_id.startswith(parent["id"] + "."):
                    errors.append(f"{relative_to_root(readme)}:{line_number}: item id {item_id} is nested under {parent['id']} but does not extend it")
                parent["children"].append(item)
            item_stack.append((level, item))
            continue

        if line.strip().startswith("- ") and "[ ]" not in line and "[x]" not in line.lower():
            errors.append(f"{relative_to_root(readme)}:{line_number}: list item inside '## Roadmap' is not a checklist item")

    if title is None:
        errors.append(f"{relative_to_root(readme)}: missing '# Title' heading")
    if not sections:
        errors.append(f"{relative_to_root(readme)}: no '## Roadmap' sections found")
    if not abilities:
        errors.append(f"{relative_to_root(readme)}: missing '**Done when you can:**' list")

    return {
        "slug": slug,
        "order": order,
        "directory": domain_directory.name,
        "title": title or slug,
        "summary": " ".join(summary_lines),
        "prerequisites": prerequisites,
        "abilities": abilities,
        "sections": sections,
    }


def collect_notes(domain_directory: pathlib.Path, errors: list[str]) -> dict[str, dict]:
    notes: dict[str, dict] = {}
    for markdown_file in sorted(domain_directory.rglob("*.md")):
        if markdown_file.name == "README.md" and markdown_file.parent == domain_directory:
            continue
        content = markdown_file.read_text(encoding="utf-8")
        for line_number, line in enumerate(content.splitlines(), 1):
            extract_links(markdown_file, line, errors, line_number)
        title_match = re.search(r"^# (.+)$", content, re.MULTILINE)
        one_sentence_match = re.search(r"^> \*\*In one sentence:\*\*\s*(.+)$", content, re.MULTILINE)
        notes[relative_to_root(markdown_file)] = {
            "title": title_match.group(1).strip() if title_match else markdown_file.stem,
            "summary": one_sentence_match.group(1).strip() if one_sentence_match else "",
            "content": content,
        }
    return notes


TRACK_ITEMS_HEADING_PATTERN = re.compile(r"^### ([a-z0-9-]+)\s*$")
TRACK_HOURS_PATTERN = re.compile(r"^\*\*Hours:\*\*\s*(.+?)\s*$")


def parse_tracks(domains: list[dict], errors: list[str]) -> list[dict]:
    tracks: list[dict] = []
    tracks_directory = REPOSITORY_ROOT / "tracks"
    if not tracks_directory.is_dir():
        return tracks
    item_ids_by_slug = {
        domain["slug"]: {item["id"] for section in domain["sections"] for item in flatten_items(section["items"])}
        for domain in domains
    }
    for track_file in sorted(tracks_directory.glob("*.md")):
        content = track_file.read_text(encoding="utf-8")
        lines = content.splitlines()
        title = next((line[2:].strip() for line in lines if line.startswith("# ")), track_file.stem)
        summary = " ".join(line[2:].strip() for line in lines if line.startswith("> "))
        hours = next((match.group(1) for line in lines if (match := TRACK_HOURS_PATTERN.match(line))), "")
        items: list[str] = []
        current_slug = None
        in_items = False
        for line_number, line in enumerate(lines, 1):
            if line.startswith("## "):
                in_items = line[3:].strip().lower() == "items"
                current_slug = None
                continue
            if not in_items:
                continue
            heading = TRACK_ITEMS_HEADING_PATTERN.match(line)
            if heading:
                current_slug = heading.group(1)
                if current_slug not in item_ids_by_slug:
                    errors.append(f"tracks/{track_file.name}:{line_number}: unknown domain '{current_slug}'")
                continue
            if current_slug and line.strip():
                for item_id in [part.strip() for part in line.split(",") if part.strip()]:
                    if current_slug in item_ids_by_slug and item_id not in item_ids_by_slug[current_slug]:
                        errors.append(f"tracks/{track_file.name}:{line_number}: item {item_id} does not exist in {current_slug}")
                    key = f"{current_slug}:{item_id}"
                    if key in items:
                        errors.append(f"tracks/{track_file.name}:{line_number}: item {key} listed twice")
                    items.append(key)
        if not items:
            errors.append(f"tracks/{track_file.name}: no '## Items' section with items")
        for line_number, line in enumerate(lines, 1):
            extract_links(track_file, line, errors, line_number)
        tracks.append({
            "slug": track_file.stem,
            "title": title,
            "summary": summary,
            "hours": hours,
            "items": items,
            "content": content,
        })
    return tracks


def flatten_items(items: list[dict]) -> list[dict]:
    flattened: list[dict] = []
    for item in items:
        flattened.append(item)
        flattened.extend(flatten_items(item["children"]))
    return flattened


def count_items(items: list[dict]) -> int:
    return sum(1 + count_items(item["children"]) for item in items)


def referenced_note_paths(items: list[dict]) -> set[str]:
    paths: set[str] = set()
    for item in items:
        for link in item["links"]:
            if link.get("path"):
                paths.add(link["path"])
        paths |= referenced_note_paths(item["children"])
    return paths


def build(check_only: bool) -> int:
    errors: list[str] = []
    warnings: list[str] = []
    domains = []
    notes: dict[str, dict] = {}

    domain_directories = sorted(
        path for path in REPOSITORY_ROOT.iterdir()
        if path.is_dir() and DOMAIN_DIRECTORY_PATTERN.match(path.name) and (path / "README.md").exists()
    )
    if not domain_directories:
        errors.append("no domain directories found (expected folders like 01-foundations/README.md)")

    for domain_directory in domain_directories:
        domain = parse_readme(domain_directory, errors)
        domain_notes = collect_notes(domain_directory, errors)
        referenced = set()
        for section in domain["sections"]:
            referenced |= referenced_note_paths(section["items"])
        for note_path in domain_notes:
            if note_path not in referenced:
                warnings.append(f"{note_path}: note is not linked from any roadmap item")
        domain["itemCount"] = sum(count_items(section["items"]) for section in domain["sections"])
        domain["noteCount"] = len(domain_notes)
        domains.append(domain)
        notes.update(domain_notes)

    known_slugs = {domain["slug"] for domain in domains}
    for domain in domains:
        for prerequisite in domain["prerequisites"]:
            if prerequisite not in known_slugs:
                errors.append(f"{domain['directory']}/README.md: unknown prerequisite domain '{prerequisite}'")

    tracks = parse_tracks(domains, errors)

    for warning in warnings:
        print(f"warning: {warning}")
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        print(f"\n{len(errors)} error(s).", file=sys.stderr)
        return 1

    data = {
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "repositoryUrl": REPOSITORY_URL,
        "branch": DEFAULT_BRANCH,
        "domains": domains,
        "notes": notes,
        "tracks": tracks,
    }
    total_items = sum(domain["itemCount"] for domain in domains)
    print(f"{len(domains)} domains, {total_items} checklist items, {len(notes)} notes, {len(tracks)} track(s).")
    for track in tracks:
        print(f"  track {track['slug']:<30} {len(track['items']):>4} items")
    for domain in domains:
        print(f"  {domain['directory']:<32} {domain['itemCount']:>4} items {domain['noteCount']:>3} notes")

    if check_only:
        print("check only, nothing written.")
        return 0

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=None, separators=(",", ":"))
    OUTPUT_FILE.write_text("window.ROADMAP_DATA = " + payload + ";\n", encoding="utf-8")
    print(f"wrote {relative_to_root(OUTPUT_FILE)} ({OUTPUT_FILE.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(build(check_only="--check" in sys.argv))
