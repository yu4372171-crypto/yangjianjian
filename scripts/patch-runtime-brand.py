"""Rebrand fixed-width records in the maintainers' prebuilt WPF shell.

The recovered desktop source already uses the correct title. This helper
retains the existing compatibility runtime while replacing its UTF-8 BAML
and UTF-16 managed-string records without changing resource offsets.
"""
from pathlib import Path
import sys


def patch(path: Path) -> dict:
    original = "AI全自动剪辑_云湃科技"
    title = "羊剪剪"
    data = path.read_bytes()
    counts = {}
    for encoding, unit in (("utf-8", 3), ("utf-16le", 2)):
        old = original.encode(encoding)
        remaining = len(old) - len(title.encode(encoding))
        if remaining % unit:
            raise ValueError("Title padding must preserve encoded resource length")
        new = (title + "\u200b" * (remaining // unit)).encode(encoding)
        if len(new) != len(old):
            raise ValueError("Title record length changed")
        counts[encoding] = data.count(old)
        data = data.replace(old, new)
    if not any(counts.values()):
        raise ValueError("Expected compatibility title records not found")
    path.write_bytes(data)
    return counts


if __name__ == "__main__":
    print(patch(Path(sys.argv[1])))
