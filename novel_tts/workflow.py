from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from novel_tts.chapter_splitter import split_chapters
from novel_tts.project import Project, create_project
from novel_tts.segmenter import split_segments
from novel_tts.ssml import build_ssml
from novel_tts.text_loader import load_text


@dataclass(frozen=True)
class PrepareResult:
    project: Project
    summary: dict


def prepare_project(
    *,
    source: Path,
    output_root: Path,
    voice: str,
    locale: str,
    rate: str,
    max_segment_chars: int = 4500,
    progress_callback: Callable[[dict], None] | None = None,
) -> PrepareResult:
    if progress_callback:
        progress_callback(
            {
                "phase": "prepare",
                "current": 0,
                "total": 0,
                "message": "正在讀取 TXT 檔...",
            }
        )
    loaded = load_text(source)

    if progress_callback:
        progress_callback(
            {
                "phase": "prepare",
                "current": 0,
                "total": 0,
                "message": f"正在分析章節... 已讀取 {len(loaded.text):,} 字",
            }
        )
    chapters = split_chapters(loaded.text)

    if progress_callback:
        progress_callback(
            {
                "phase": "prepare",
                "current": 0,
                "total": 0,
                "message": f"正在建立專案資料夾... 共 {len(chapters)} 章",
            }
        )
    project = create_project(
        source_path=source,
        output_root=output_root,
        encoding=loaded.encoding,
        chapters=chapters,
        voice=voice,
        locale=locale,
        rate=rate,
    )

    total_segments = 0
    ssml_dir = project.root / "temp" / "ssml"
    segments_dir = project.root / "temp" / "segments"

    total_chapters = len(chapters)
    if progress_callback:
        progress_callback(
            {
                "phase": "prepare",
                "current": 0,
                "total": total_chapters,
                "message": f"準備專案：0 / {total_chapters} 章",
            }
        )

    for chapter_position, chapter in enumerate(chapters, start=1):
        segments = split_segments(chapter.text, max_chars=max_segment_chars)
        total_segments += len(segments)
        chapter_prefix = f"{chapter.index:04d}"

        for segment in segments:
            segment_id = f"{chapter_prefix}_{segment.index:04d}"
            (segments_dir / f"{segment_id}.txt").write_text(segment.text, encoding="utf-8")
            ssml = build_ssml(
                text=segment.text,
                voice=voice,
                locale=locale,
                rate=rate,
            )
            (ssml_dir / f"{segment_id}.ssml").write_text(ssml, encoding="utf-8")

        if progress_callback:
            progress_callback(
                {
                    "phase": "prepare",
                    "current": chapter_position,
                    "total": total_chapters,
                    "chapter": chapter.index,
                    "message": f"準備專案：{chapter_position} / {total_chapters} 章，已切出 {total_segments} 段",
                }
            )

    summary = {
        "project": str(project.root),
        "source": str(source),
        "encoding": loaded.encoding,
        "characters": len(loaded.text),
        "chapters": len(chapters),
        "segments": total_segments,
        "voice": voice,
        "locale": locale,
        "rate": rate,
        "estimated_free_azure_months_at_500k_chars": round(len(loaded.text) / 500_000, 2),
    }
    return PrepareResult(project=project, summary=summary)


def summary_json(summary: dict) -> str:
    return json.dumps(summary, ensure_ascii=False, indent=2)
