from __future__ import annotations

import re
from dataclasses import dataclass


CHAPTER_PATTERN = re.compile(
    r"^\s*(?:"
    r"(?:第\s*[0-9零〇一二兩三四五六七八九十百千萬两]+\s*[章回卷節节].*)"
    r"|(?:chapter\s+\d+.*)"
    r"|(?:ch\.\s*\d+.*)"
    r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class Chapter:
    index: int
    title: str
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)


def split_chapters(text: str) -> list[Chapter]:
    matches = list(CHAPTER_PATTERN.finditer(text))
    if not matches:
        return [Chapter(index=1, title="全文", text=text.strip())]

    chapters: list[Chapter] = []

    preface = text[: matches[0].start()].strip()
    if preface:
        chapters.append(Chapter(index=1, title="序章", text=preface))

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        title = match.group(0).strip() or f"Chapter {i + 1}"
        chapters.append(Chapter(index=len(chapters) + 1, title=title, text=chunk))

    return chapters

