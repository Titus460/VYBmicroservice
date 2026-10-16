#!/usr/bin/env python3
"""Fail CI when tracked files contain high-confidence credentials.

Only finding types and paths are printed. Secret values are never emitted.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


FORBIDDEN_PATHS = {
    "vibr_config.json",
    "vibr_registration_config.json",
    "Model/Common/Config.json",
}
FORBIDDEN_NAME_PATTERNS = (
    re.compile(r"(^|/)icebreakerfinal-firebase-adminsdk-.*\.json$", re.I),
    re.compile(r"\.(pem|key|p12|pfx|jks|keystore)$", re.I),
)
SECRET_PATTERNS = {
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "private key": re.compile(rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    "OpenAI-style key": re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Google API key": re.compile(rb"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "GitHub token": re.compile(rb"\bgh[pousr]_[0-9A-Za-z]{20,}\b"),
    "Slack token": re.compile(rb"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TRACKED_FILES_MANIFEST = REPOSITORY_ROOT / ".tracked-files"


def tracked_files() -> list[str]:
    if shutil.which("git") is not None:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            check=True,
            capture_output=True,
            cwd=REPOSITORY_ROOT,
        )
        raw_paths = result.stdout
    elif TRACKED_FILES_MANIFEST.is_file():
        raw_paths = TRACKED_FILES_MANIFEST.read_bytes()
    else:
        raise RuntimeError(
            "git is unavailable and the tracked-files manifest is missing"
        )

    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in raw_paths.split(b"\0")
        if item
    ]


def main() -> int:
    findings: list[tuple[str, str]] = []
    for relative_path in tracked_files():
        normalized = relative_path.replace("\\", "/")
        if normalized in FORBIDDEN_PATHS or any(
            pattern.search(normalized) for pattern in FORBIDDEN_NAME_PATTERNS
        ):
            findings.append(("forbidden credential file", normalized))

        path = REPOSITORY_ROOT / relative_path
        if not path.is_file():
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if b"\0" in content[:8192]:
            continue
        for finding_type, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                findings.append((finding_type, normalized))

    if findings:
        print("ERROR: tracked credential material detected:")
        for finding_type, path in sorted(set(findings)):
            print(f"  {finding_type}: {path}")
        print("Move values to Kubernetes Secrets; do not suppress this gate.")
        return 1

    print("SUCCESS: no high-confidence credentials found in tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
