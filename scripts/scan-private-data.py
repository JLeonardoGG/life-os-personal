from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOCKED_EXTENSIONS = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".xml",
    ".zip",
    ".pdf",
    ".csv",
    ".tsv",
    ".xls",
    ".xlsx",
    ".ofx",
    ".qfx",
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
}
ALLOWED_BINARY_PREFIXES = ("docs/assets/", "tests/fixtures/", "demo/")
PATTERNS = {
    "absolute-user-path": re.compile("/" + r"Users/[A-Za-z0-9._-]+"),
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "filled-api-key": re.compile(r"(?m)^LIFE_OS_API_KEY=\\S+"),
    "filled-session-secret": re.compile(r"(?m)^LIFE_OS_SESSION_SECRET=\\S+"),
    "mexican-rfc": re.compile(r"\\b[A-Z&Ñ]{3,4}\\d{6}[A-Z0-9]{3}\\b"),
}
RFC_ALLOWLIST = {"XAXX010101000", "XEXX010101000", "COSC8001137NA"}


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [ROOT / item.decode() for item in output.split(b"\0") if item]


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if relative == "scripts/scan-private-data.py":
            continue
        if path.suffix.lower() in BLOCKED_EXTENSIONS and not relative.startswith(ALLOWED_BINARY_PREFIXES):
            findings.append(f"{relative}: extension privada no permitida")
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                if label == "mexican-rfc" and match.group(0) in RFC_ALLOWLIST:
                    continue
                findings.append(f"{relative}:{text.count(chr(10), 0, match.start()) + 1}: {label}")
    if findings:
        print("Posibles datos privados encontrados:")
        print("\n".join(f"- {item}" for item in findings))
        return 1
    print("Escaneo de privacidad: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
