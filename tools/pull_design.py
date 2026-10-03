"""Pull a Claude Design file straight from the design server.

No Claude chat and no file export. Claude Code's design login
(~/.claude/.credentials.json, key designOauth) is sent to the design MCP.
A read is capped at 256 KiB, so large files are fetched in line windows
and joined back together.

The Nebula project is the default, so this needs no URL:

    python tools/pull_design.py

That writes Nebula Update Window.dc.html and Prefs Update Window.dc.html
into design/update-window/.

    python tools/pull_design.py --file "Nebula Toast Row.dc.html" --into design/toast-row
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP_URL = "https://api.anthropic.com/v1/design/mcp"
NEBULA_PROJECT = "19d87879-67c8-4a4e-8eb1-d4fbd327a23a"
NEBULA_URL = "https://claude.ai/design/p/" + NEBULA_PROJECT
UPDATE_FILES = (
    "Nebula Update Window.dc.html",
    "Prefs Update Window.dc.html",
)
# Lines per call. The server also stops at 256 KiB; a short page stays under that.
PAGE_LINES = 400
_WRAP = re.compile(
    r"<untrusted-project-content\b([^>]*)>(.*)</untrusted-project-content>",
    re.DOTALL,
)
_ATTR = re.compile(r'([\w:-]+)="([^"]*)"')


class DesignError(RuntimeError):
    pass


def _token() -> str:
    path = os.path.join(os.path.expanduser("~"), ".claude", ".credentials.json")
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DesignError(
            "No design login at %s. Open Claude Code once so it can sign in."
            % path
        ) from exc
    oauth = data.get("designOauth") or {}
    token = oauth.get("accessToken") or ""
    if not token:
        raise DesignError("Design login has no access token. Open Claude Code once.")
    return token


def _dest(into: str) -> str:
    raw = into.replace("\\", "/").strip("/")
    if not raw.startswith("design/") or ".." in raw.split("/"):
        raise DesignError("--into must be a folder under design/")
    path = os.path.normpath(os.path.join(ROOT, *raw.split("/")))
    design = os.path.normpath(os.path.join(ROOT, "design"))
    if os.path.commonpath([design, path]) != design:
        raise DesignError("--into escapes design/")
    return path


class _Mcp:
    def __init__(self, token: str):
        self._token = token
        self._id = 0
        self._post({
            "jsonrpc": "2.0",
            "id": self._next(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "nebula-pull-design", "version": "0.2"},
            },
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _next(self) -> int:
        self._id += 1
        return self._id

    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(
            MCP_URL,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": "Bearer " + self._token,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise DesignError("Design server returned %s. %s" % (exc.code, detail)) from exc
        if not raw:
            return {}
        data = json.loads(raw)
        if data.get("error"):
            raise DesignError(data["error"].get("message") or "design MCP error")
        return data

    def call(self, name: str, arguments: dict) -> str:
        data = self._post({
            "jsonrpc": "2.0",
            "id": self._next(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        result = data.get("result") or {}
        if result.get("isError"):
            bits = result.get("content") or []
            text = bits[0].get("text") if bits else "design tool failed"
            raise DesignError(text)
        bits = result.get("content") or []
        if not bits:
            raise DesignError("%s returned nothing" % name)
        return bits[0].get("text") or ""


def _window(text: str) -> tuple[str, int, int]:
    match = _WRAP.search(text)
    if not match:
        raise DesignError(text.strip()[:300] or "design read had no file body")
    attrs = dict(_ATTR.findall(match.group(1)))
    lines = attrs.get("lines") or ""
    span = lines.split("-")
    if len(span) != 2:
        raise DesignError("design read did not say which lines it returned")
    _start, end = int(span[0]), int(span[1])
    total = int(attrs.get("total_lines") or end)
    body = match.group(2)
    if body.startswith("\n"):
        body = body[1:]
    if body.endswith("\n"):
        body = body[:-1]
    return html.unescape(body), end, total


def read_file(mcp: _Mcp, project: str, path: str) -> str:
    parts: list[str] = []
    offset = 1
    total = None
    while True:
        text = mcp.call("read_file", {
            "project_id": project,
            "path": path,
            "offset": offset,
            "limit": PAGE_LINES,
        })
        body, end, total = _window(text)
        parts.append(body)
        if end >= total:
            break
        if end < offset:
            raise DesignError("design read did not advance at %s" % path)
        offset = end + 1
    file = "\n".join(parts)
    if total and file.count("\n") + (0 if file.endswith("\n") or not file else 1) < total:
        # A joined window should cover every line. Count non-empty splits loosely.
        got = 0 if not file else file.count("\n") + 1
        if got < total:
            raise DesignError(
                "%s came back short (%s lines of %s). Not saved."
                % (path, got, total)
            )
    if file and not file.endswith("\n"):
        file += "\n"
    return file


def _project_and_files(url: str | None, files: list[str], into: str) -> tuple[str, list[str]]:
    project = NEBULA_PROJECT
    chosen = list(files)
    if url:
        match = re.search(r"/p/([0-9a-f-]{36})", url)
        if not match:
            raise DesignError("URL has no design project id")
        project = match.group(1)
        query = re.search(r"[?&]file=([^&]+)", url)
        if query and not chosen:
            from urllib.parse import unquote
            chosen = [unquote(query.group(1)).replace("+", " ")]
    if not chosen and into.replace("\\", "/").strip("/") == "design/update-window":
        chosen = list(UPDATE_FILES)
    if not chosen:
        raise DesignError("Pass --file, or a URL with ?file=, or use the update-window default.")
    return project, chosen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="claude.ai/design link. Defaults to the Nebula project.")
    parser.add_argument("--file", action="append", default=[], help="project path to read. Repeatable.")
    parser.add_argument("--into", default="design/update-window", help="folder under design/")
    args = parser.parse_args()
    try:
        dest = _dest(args.into)
        project, files = _project_and_files(args.url, args.file, args.into)
        os.makedirs(dest, exist_ok=True)
        mcp = _Mcp(_token())
        written = []
        for name in files:
            body = read_file(mcp, project, name)
            path = os.path.join(dest, os.path.basename(name.replace("\\", "/")))
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
            written.append(os.path.relpath(path, ROOT))
            print("wrote %s (%s bytes)" % (written[-1], len(body.encode("utf-8"))))
    except DesignError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not written:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
