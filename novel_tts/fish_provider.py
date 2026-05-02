from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from novel_tts.audio_merge import create_chapter_audio
from novel_tts.cli_helpers import read_chapter_segments, select_chapters
from novel_tts.project import Project, update_chapter
from novel_tts.segmenter import split_segments


DEFAULT_FISH_SERVER_URL = "http://127.0.0.1:8080/v1/tts"
DEFAULT_FISH_XPU_SERVER_URL = "http://127.0.0.1:8081/v1/tts"
DEFAULT_FISH_MAX_CHARS = 500
DEFAULT_FISH_MAX_NEW_TOKENS = 32


@dataclass(frozen=True)
class FishResult:
    chapter: int
    status: str
    output: str | None = None
    error: str | None = None


def synthesize_project_fish(
    *,
    project: Project,
    chapter: int | None = None,
    force: bool = False,
    server_url: str = DEFAULT_FISH_SERVER_URL,
    api_key: str = "",
    reference_id: str = "",
    seed: int | None = None,
    max_chunk_chars: int = DEFAULT_FISH_MAX_CHARS,
    chunk_length: int = 300,
    max_new_tokens: int = DEFAULT_FISH_MAX_NEW_TOKENS,
    top_p: float = 0.8,
    temperature: float = 0.8,
    repetition_penalty: float = 1.1,
    ffmpeg: str = "ffmpeg",
    progress_callback: Callable[[dict], None] | None = None,
) -> list[FishResult]:
    manifest = project.load_manifest()
    selected = select_chapters(manifest["chapters"], chapter)
    prepared: list[tuple[dict, list[tuple[int, str]] | None]] = []
    total_segments = 0

    for chapter_record in selected:
        if chapter_record.get("status") == "done" and not force:
            prepared.append((chapter_record, None))
            continue
        segments = split_fish_segments(
            read_chapter_segments(project.root, chapter_record["index"]),
            max_chars=max_chunk_chars,
        )
        prepared.append((chapter_record, segments))
        total_segments += len(segments)

    completed_segments = 0
    total_segments = max(total_segments, 1)
    if progress_callback:
        progress_callback(
            {
                "phase": "fish",
                "current": 0,
                "total": total_segments,
                "message": f"Fish Speech：0 / {total_segments} 段",
            }
        )

    results: list[FishResult] = []
    for chapter_position, (chapter_record, segments) in enumerate(prepared, start=1):
        chapter_index = chapter_record["index"]
        if chapter_record.get("status") == "done" and not force:
            results.append(FishResult(chapter=chapter_index, status="skipped", output=chapter_record.get("output")))
            continue

        try:
            update_chapter(project, chapter_index, status="running", provider="fish-speech", error=None)
            if not segments:
                raise RuntimeError("No text segments found")

            work_dir = project.root / "temp" / "fish" / f"{chapter_index:04d}"
            work_dir.mkdir(parents=True, exist_ok=True)
            segment_outputs: list[Path] = []
            chapter_total_segments = len(segments)

            for segment_position, (segment_index, text) in enumerate(segments, start=1):
                output = work_dir / f"{chapter_index:04d}_{segment_index:04d}.mp3"
                request_fish_tts(
                    text=text,
                    output=output,
                    server_url=server_url,
                    api_key=api_key,
                    reference_id=reference_id,
                    seed=seed,
                    chunk_length=chunk_length,
                    max_new_tokens=max_new_tokens,
                    top_p=top_p,
                    temperature=temperature,
                    repetition_penalty=repetition_penalty,
                )
                segment_outputs.append(output)
                completed_segments += 1
                if progress_callback:
                    progress_callback(
                        {
                            "phase": "fish",
                            "current": completed_segments,
                            "total": total_segments,
                            "chapter": chapter_index,
                            "chapter_position": chapter_position,
                            "chapter_total": len(prepared),
                            "segment": segment_position,
                            "segment_total": chapter_total_segments,
                            "message": (
                                f"Fish Speech：第 {chapter_position} / {len(prepared)} 章，"
                                f"段落 {segment_position} / {chapter_total_segments}，"
                                f"總進度 {completed_segments} / {total_segments} 段"
                            ),
                        }
                    )

            output_path = project.root / chapter_record["output"]
            create_chapter_audio(segment_outputs, output_path, ffmpeg=ffmpeg)
            update_chapter(project, chapter_index, status="done", output=str(output_path.relative_to(project.root)))
            results.append(FishResult(chapter=chapter_index, status="done", output=str(output_path)))
        except Exception as exc:
            update_chapter(project, chapter_index, status="failed", error=str(exc))
            results.append(FishResult(chapter=chapter_index, status="failed", error=str(exc)))

    return results


def request_fish_tts(
    *,
    text: str,
    output: Path,
    server_url: str,
    api_key: str = "",
    reference_id: str = "",
    seed: int | None = None,
    chunk_length: int = 300,
    max_new_tokens: int = DEFAULT_FISH_MAX_NEW_TOKENS,
    top_p: float = 0.8,
    temperature: float = 0.8,
    repetition_penalty: float = 1.1,
) -> Path:
    try:
        import ormsgpack
    except ImportError as exc:
        raise RuntimeError("Fish Speech API mode requires ormsgpack. Install requirements-fish.txt.") from exc

    data = {
        "text": text,
        "references": [],
        "reference_id": reference_id.strip() or None,
        "format": "mp3",
        "latency": "normal",
        "max_new_tokens": max(1, int(max_new_tokens)),
        "chunk_length": chunk_length,
        "top_p": top_p,
        "repetition_penalty": repetition_penalty,
        "temperature": temperature,
        "streaming": False,
        "use_memory_cache": "off",
        "seed": seed,
    }
    headers = {"content-type": "application/msgpack"}
    if api_key.strip():
        headers["authorization"] = f"Bearer {api_key.strip()}"

    response = requests.post(
        server_url,
        params={"format": "msgpack"},
        data=ormsgpack.packb(data),
        headers=headers,
        timeout=600,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Fish Speech API failed ({response.status_code}): {response.text}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(response.content)
    return output


def split_fish_segments(segments: list[tuple[int, str]], *, max_chars: int) -> list[tuple[int, str]]:
    output: list[tuple[int, str]] = []
    for _, text in segments:
        for segment in split_segments(text, max_chars=max_chars):
            output.append((len(output) + 1, segment.text))
    return output
