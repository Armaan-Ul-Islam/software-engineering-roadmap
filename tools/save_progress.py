#!/usr/bin/env python3
"""Save a progress file downloaded from the tracker into progress/<profile>.json.

Usage:
    python3 tools/save_progress.py ~/Downloads/armaan.json            # profile name from the file
    python3 tools/save_progress.py ~/Downloads/roadmap.json --name me  # override the profile name
    python3 tools/save_progress.py ~/Downloads/armaan.json --commit    # also commit the result locally

The file is validated, normalised (sorted keys, two-space indent) and written to progress/,
then tools/build.py runs so site/data.js carries the new baseline.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")


def main(arguments: list[str]) -> int:
    if not arguments or arguments[0].startswith("--"):
        print(__doc__)
        return 2
    source = pathlib.Path(arguments[0]).expanduser()
    name_override = None
    commit = "--commit" in arguments
    if "--name" in arguments:
        name_override = arguments[arguments.index("--name") + 1]

    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("format") != "software-engineering-roadmap-progress" or not isinstance(payload.get("progress"), dict):
        print("error: not a tracker progress file (missing format or progress fields)", file=sys.stderr)
        return 1
    profile = (name_override or payload.get("profile") or source.stem).strip().lower()
    if not PROFILE_NAME_PATTERN.match(profile):
        print(f"error: profile name '{profile}' must be 1-40 characters of a-z, 0-9, dot, dash or underscore", file=sys.stderr)
        return 1

    progress = {key: value for key, value in payload["progress"].items() if value and ":" in key}
    normalised = {
        "format": "software-engineering-roadmap-progress",
        "version": 1,
        "profile": profile,
        "exportedAt": payload.get("exportedAt", ""),
        "progress": dict(sorted(progress.items())),
    }
    target = REPOSITORY_ROOT / "progress" / f"{profile}.json"
    target.write_text(json.dumps(normalised, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {target.relative_to(REPOSITORY_ROOT)} with {len(progress)} completed items")

    build = subprocess.run([sys.executable, str(REPOSITORY_ROOT / "tools" / "build.py")], cwd=REPOSITORY_ROOT)
    if build.returncode != 0:
        return build.returncode
    if commit:
        subprocess.run(["git", "add", str(target), "site/data.js"], cwd=REPOSITORY_ROOT, check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"Save progress for {profile}"], cwd=REPOSITORY_ROOT, check=True)
        print("committed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
