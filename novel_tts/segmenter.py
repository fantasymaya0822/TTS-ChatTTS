from __future__ import annotations

import re
from dataclasses import dataclass


BOUNDARY_PATTERN = re.compile(r"(?<=[。！？!?；;」』”\n])")


@dataclass(frozen=True)
class Segment:
    index: int
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)


def split_segments(text: str, max_chars: int = 4500) -> list[Segment]:
    normalized = normalize_text(text)
    if len(normalized) <= max_chars:
        return [Segment(index=1, text=normalized)]

    pieces = [piece for piece in BOUNDARY_PATTERN.split(normalized) if piece]
    segments: list[str] = []
    current = ""

    for piece in pieces:
        if len(piece) > max_chars:
            if current:
                segments.append(current.strip())
                current = ""
            segments.extend(hard_split(piece, max_chars))
            continue

        if current and len(current) + len(piece) > max_chars:
            segments.append(current.strip())
            current = piece
        else:
            current += piece

    if current.strip():
        segments.append(current.strip())

    return [Segment(index=i + 1, text=segment) for i, segment in enumerate(segments)]


def hard_split(text: str, max_chars: int) -> list[str]:
    return [text[i : i + max_chars].strip() for i in range(0, len(text), max_chars) if text[i : i + max_chars].strip()]


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()

