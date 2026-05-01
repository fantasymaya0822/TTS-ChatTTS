from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from charset_normalizer import from_bytes


@dataclass(frozen=True)
class LoadedText:
    text: str
    encoding: str


def load_text(path: Path) -> LoadedText:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "big5", "cp950", "gb18030"):
        try:
            return LoadedText(text=raw.decode(encoding), encoding=encoding)
        except UnicodeDecodeError:
            continue

    detected = from_bytes(raw).best()
    if detected is None:
        raise UnicodeDecodeError("unknown", raw, 0, 1, "Could not detect text encoding")

    return LoadedText(text=str(detected), encoding=detected.encoding or "unknown")

