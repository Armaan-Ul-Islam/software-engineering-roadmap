#!/usr/bin/env python3
"""Check every external link in the repository's markdown files.

Usage:
    python3 tools/check_links.py                 # check all markdown files
    python3 tools/check_links.py 05-java         # check files under a folder
    python3 tools/check_links.py --timeout 20    # per-request timeout in seconds

Links are classified as OK (2xx/3xx), BLOCKED (401/403/429/999: the site refuses automated
clients, check by hand), or BROKEN (404/410/5xx, DNS failures, timeouts). The exit code is
1 when any link is BROKEN. A report is written to tools/link-report.txt.
"""

from __future__ import annotations

import concurrent.futures
import pathlib
import re
import ssl
import sys
import urllib.error
import urllib.request

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT_FILE = REPOSITORY_ROOT / "tools" / "link-report.txt"
LINK_PATTERN = re.compile(r"\]\((https?://[^)\s]+)\)")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 roadmap-link-check/1.0"
)
BLOCKED_STATUSES = {401, 403, 406, 429, 999}
# Hosts that reject non-browser clients at the connection level; report them as BLOCKED, not BROKEN.
MANUAL_CHECK_HOSTS = {"cwe.mitre.org", "itrevolution.com", "www.uber.com"}


def collect_links(paths: list[pathlib.Path]) -> dict[str, set[str]]:
    links: dict[str, set[str]] = {}
    for path in paths:
        files = [path] if path.is_file() else sorted(path.rglob("*.md"))
        for markdown_file in files:
            if "site/" in markdown_file.as_posix() or ".git/" in markdown_file.as_posix():
                continue
            for line_number, line in enumerate(markdown_file.read_text(encoding="utf-8").splitlines(), 1):
                for url in LINK_PATTERN.findall(line):
                    url = url.rstrip(".,;")
                    links.setdefault(url, set()).add(f"{markdown_file.relative_to(REPOSITORY_ROOT).as_posix()}:{line_number}")
    return links


def fetch_status(url: str, timeout: float) -> tuple[str, str]:
    from urllib.parse import urlparse
    if urlparse(url).netloc.lower() in MANUAL_CHECK_HOSTS:
        return "BLOCKED", "manual"
    context = ssl.create_default_context()
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                return "OK", str(response.status)
        except urllib.error.HTTPError as http_error:
            if method == "HEAD" and http_error.code in (400, 403, 404, 405, 406, 429, 500, 501, 503):
                continue
            if http_error.code in BLOCKED_STATUSES:
                return "BLOCKED", str(http_error.code)
            return "BROKEN", str(http_error.code)
        except urllib.error.URLError as url_error:
            if method == "HEAD":
                continue
            return "BROKEN", f"{type(url_error.reason).__name__}: {url_error.reason}"
        except TimeoutError:
            if method == "HEAD":
                continue
            return "BROKEN", "timeout"
        except Exception as exception:  # noqa: BLE001 - report anything else as broken
            if method == "HEAD":
                continue
            return "BROKEN", f"{type(exception).__name__}: {exception}"
    return "BROKEN", "unreachable"


def main(arguments: list[str]) -> int:
    timeout = 15.0
    paths: list[pathlib.Path] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--timeout":
            timeout = float(arguments[index + 1])
            index += 2
            continue
        paths.append((REPOSITORY_ROOT / argument).resolve())
        index += 1
    if not paths:
        paths = [REPOSITORY_ROOT]

    links = collect_links(paths)
    print(f"checking {len(links)} unique links with {timeout:.0f}s timeout ...")

    results: dict[str, tuple[str, str]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        future_to_url = {executor.submit(fetch_status, url, timeout): url for url in links}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            results[url] = future.result()

    grouped: dict[str, list[str]] = {"BROKEN": [], "BLOCKED": [], "OK": []}
    for url, (status, detail) in results.items():
        grouped[status].append(url)

    report_lines = []
    for status in ("BROKEN", "BLOCKED"):
        if grouped[status]:
            report_lines.append(f"== {status} ({len(grouped[status])}) ==")
            for url in sorted(grouped[status]):
                detail = results[url][1]
                locations = ", ".join(sorted(links[url]))
                report_lines.append(f"{detail:>8}  {url}\n          at {locations}")
    report_lines.append(f"== OK ({len(grouped['OK'])}) ==")
    report = "\n".join(report_lines)
    REPORT_FILE.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\nreport written to {REPORT_FILE.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 1 if grouped["BROKEN"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
