#!/usr/bin/env python3
"""Claude Code PreToolUse hook for Edit, Write and MultiEdit.

Blocks (exit code 2, reason on stderr so Claude can correct course):
- writing to .env files, secrets/, key files or .git/
- content that looks like a private key, an Anthropic or AWS key, or a hard-coded password
- self-approving real money: live mode, autonomy 3+ or the live-approval token
Edits to risk code are not blocked here; .claude/settings.json makes them ask the human.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import PurePosixPath

BLOCKED_PARTS = {".git", "secrets"}
BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"), "an Anthropic API key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "an AWS access key"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|api[_-]?secret|secret[_-]?key|password|passwd)\b\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"
        ),
        "a hard-coded credential",
    ),
]
TOKEN_PATTERN = re.compile(r"QUANTAGENTS_LIVE_APPROVED\s*=\s*[\"']?I_ACCEPT_REAL_MONEY_RISK")
YAML_PATTERNS = [
    (re.compile(r"(?m)^\s*live_trading_approved:\s*true\b"), "live_trading_approved: true"),
    (re.compile(r"(?m)^\s*execution_mode:\s*live\b"), "execution_mode: live"),
    (re.compile(r"(?m)^\s*autonomy_level:\s*[34]\b"), "autonomy level 3 or 4"),
]
HUMAN_ONLY = (
    "is a human-only decision (spec sections 2 and 65). Ask the owner to change it by hand."
)


def blocked_path(file_path: str) -> str | None:
    path = PurePosixPath(file_path.replace("\\", "/"))
    name = path.name
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return "secrets live in .env, which only the human edits (spec section 72)"
    if BLOCKED_PARTS & set(path.parts):
        return "this folder is off limits to automated edits"
    if path.suffix.lower() in BLOCKED_SUFFIXES:
        return "key and certificate files are never written by Claude"
    return None


def new_text(tool_input: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ("content", "new_string"):
        value = tool_input.get(key)
        if isinstance(value, str):
            parts.append(value)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        parts.extend(str(e.get("new_string", "")) for e in edits if isinstance(e, dict))
    return "\n".join(parts)


def check(payload: dict[str, object]) -> str | None:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    file_path = str(tool_input.get("file_path", ""))
    reason = blocked_path(file_path) if file_path else None
    if reason:
        return f"Blocked edit to {file_path}: {reason}."
    text = new_text(tool_input)
    for pattern, label in SECRET_PATTERNS:
        if pattern.search(text):
            return f"Blocked: the new content contains {label}. Load secrets from the environment instead."
    if TOKEN_PATTERN.search(text):
        return f"Blocked: setting the live-trading approval token {HUMAN_ONLY}"
    if file_path.endswith((".yaml", ".yml")):
        for pattern, label in YAML_PATTERNS:
            if pattern.search(text):
                return f"Blocked: {label} {HUMAN_ONLY}"
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    reason = check(payload)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
