from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import edge_tts

from novel_tts.audio_merge import create_chapter_audio
from novel_tts.cli_helpers import read_chapter_segments, select_chapters
from novel_tts.project import Project, update_chapter


DEFAULT_EDGE_VOICE = "zh-TW-HsiaoChenNeural"


@dataclass(frozen=True)
class EdgeResult:
    chapter: int
    status: str
    output: str | None = None
    error: str | None = None


async def list_edge_voices(locale: str | None = "zh-TW") -> list[dict]:
    voices = await edge_tts.list_voices()
    if not locale:
        return voices
    return [
        voice
        for voice in voices
        if voice.get("Locale", "").lower() == locale.lower()
    ]


def list_edge_voices_sync(locale: str | None = "zh-TW") -> list[dict]:
    return asyncio.run(list_edge_voices(locale))


def synthesize_project_edge(
    *,
    project: Project,
    voice: str,
    rate: str,
    chapter: int | None = None,
    force: bool = False,
    ffmpeg: str = "ffmpeg",
    progress_callback: Callable[[dict], None] | None = None,
) -> list[EdgeResult]:
    return asyncio.run(
        synthesize_project_edge_async(
            project=project,
            voice=voice,
            rate=rate,
            chapter=chapter,
            force=force,
            ffmpeg=ffmpeg,
            progress_callback=progress_callback,
        )
    )


async def synthesize_project_edge_async(
    *,
    project: Project,
    voice: str,
    rate: str,
    chapter: int | None = None,
    force: bool = False,
    ffmpeg: str = "ffmpeg",
    progress_callback: Callable[[dict], None] | None = None,
) -> list[EdgeResult]:
    manifest = project.load_manifest()
    selected = select_chapters(manifest["chapters"], chapter)
    results: list[EdgeResult] = []
    prepared: list[tuple[dict, list[tuple[int, str]] | None]] = []
    total_segments = 0

    for chapter_record in selected:
        if chapter_record.get("status") == "done" and not force:
            prepared.append((chapter_record, None))
            continue
        segments = read_chapter_segments(project.root, chapter_record["index"])
        prepared.append((chapter_record, segments))
        total_segments += len(segments)

    completed_segments = 0
    total_segments = max(total_segments, 1)
    if progress_callback:
        progress_callback(
            {
                "phase": "edge",
                "current": 0,
                "total": total_segments,
                "message": f"Edge TTS：0 / {total_segments} 段",
            }
        )

    for chapter_position, (chapter_record, prepared_segments) in enumerate(prepared, start=1):
        chapter_index = chapter_record["index"]
        if chapter_record.get("status") == "done" and not force:
            results.append(
                EdgeResult(
                    chapter=chapter_index,
                    status="skipped",
                    output=chapter_record.get("output"),
                )
            )
            continue

        try:
            update_chapter(project, chapter_index, status="running", provider="edge-tts", error=None)
            segments = prepared_segments or []
            if not segments:
                raise RuntimeError("No text segments found")

            segment_outputs: list[Path] = []
            work_dir = project.root / "temp" / "edge" / f"{chapter_index:04d}"
            work_dir.mkdir(parents=True, exist_ok=True)

            chapter_total_segments = len(segments)
            for segment_position, (segment_index, text) in enumerate(segments, start=1):
                output = work_dir / f"{chapter_index:04d}_{segment_index:04d}.mp3"
                communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
                await communicate.save(str(output))
                segment_outputs.append(output)
                completed_segments += 1
                if progress_callback:
                    progress_callback(
                        {
                            "phase": "edge",
                            "current": completed_segments,
                            "total": total_segments,
                            "chapter": chapter_index,
                            "chapter_position": chapter_position,
                            "chapter_total": len(prepared),
                            "segment": segment_position,
                            "segment_total": chapter_total_segments,
                            "message": (
                                f"Edge TTS：第 {chapter_position} / {len(prepared)} 章，"
                                f"段落 {segment_position} / {chapter_total_segments}，"
                                f"總進度 {completed_segments} / {total_segments} 段"
                            ),
                        }
                    )

            output_path = project.root / chapter_record["output"]
            create_chapter_audio(segment_outputs, output_path, ffmpeg=ffmpeg)
            update_chapter(project, chapter_index, status="done", output=str(output_path.relative_to(project.root)))
            results.append(EdgeResult(chapter=chapter_index, status="done", output=str(output_path)))
        except Exception as exc:
            update_chapter(project, chapter_index, status="failed", error=str(exc))
            results.append(EdgeResult(chapter=chapter_index, status="failed", error=str(exc)))

    return results
