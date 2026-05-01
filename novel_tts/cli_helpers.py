from __future__ import annotations

from pathlib import Path


def read_chapter_segments(project_root: Path, chapter_index: int) -> list[tuple[int, str]]:
    segments_dir = project_root / "temp" / "segments"
    prefix = f"{chapter_index:04d}_"
    segments: list[tuple[int, str]] = []
    for path in sorted(segments_dir.glob(f"{prefix}*.txt")):
        segment_index = int(path.stem.split("_", 1)[1])
        segments.append((segment_index, path.read_text(encoding="utf-8")))
    return segments


def read_chapter_ssml(project_root: Path, chapter_index: int) -> list[str]:
    ssml_dir = project_root / "temp" / "ssml"
    prefix = f"{chapter_index:04d}_"
    return [
        path.read_text(encoding="utf-8")
        for path in sorted(ssml_dir.glob(f"{prefix}*.ssml"))
    ]


def select_chapters(chapters: list[dict], chapter: int | None) -> list[dict]:
    if chapter is None:
        return chapters
    return [item for item in chapters if item["index"] == chapter]
