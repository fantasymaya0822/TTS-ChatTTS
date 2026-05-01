from __future__ import annotations

import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from novel_tts.audio_merge import convert_to_mp3, create_chapter_audio
from novel_tts.cli_helpers import read_chapter_segments, select_chapters
from novel_tts.project import Project, update_chapter
from novel_tts.segmenter import split_segments


DEFAULT_CHAT_PROMPT = "[oral_2][laugh_0][break_4]"
DEFAULT_PREVIEW_TEXT = "這是一段 ChatTTS 聲音試聽。請確認這個聲音是否適合用來朗讀小說。"
DEFAULT_CHAT_MAX_CHARS = 180


@dataclass(frozen=True)
class ChatTtsResult:
    chapter: int
    status: str
    output: str | None = None
    error: str | None = None


def synthesize_project_chattts(
    *,
    project: Project,
    chapter: int | None = None,
    force: bool = False,
    prompt: str = DEFAULT_CHAT_PROMPT,
    skip_refine_text: bool = False,
    speaker_seed: int | None = None,
    source: str = "huggingface",
    custom_path: str | None = None,
    ffmpeg: str = "ffmpeg",
    progress_callback: Callable[[dict], None] | None = None,
    max_chunk_chars: int = DEFAULT_CHAT_MAX_CHARS,
) -> list[ChatTtsResult]:
    chat_module = import_chattts()
    chat = chat_module.Chat()
    loaded = chat.load(source=source, custom_path=custom_path, compile=False)
    if not loaded:
        raise RuntimeError("ChatTTS model failed to load.")

    params_refine_text = chat_module.Chat.RefineTextParams(prompt=prompt)
    params_infer_code = build_infer_params(chat_module, chat, speaker_seed)
    manifest = project.load_manifest()
    selected = select_chapters(manifest["chapters"], chapter)
    results: list[ChatTtsResult] = []
    prepared: list[tuple[dict, list[tuple[int, str]] | None]] = []
    total_segments = 0

    for chapter_record in selected:
        if chapter_record.get("status") == "done" and not force:
            prepared.append((chapter_record, None))
            continue
        segments = read_chapter_segments(project.root, chapter_record["index"])
        chattts_segments = split_chattts_segments(segments, max_chars=max_chunk_chars)
        prepared.append((chapter_record, chattts_segments))
        total_segments += len(chattts_segments)

    completed_segments = 0
    total_segments = max(total_segments, 1)
    if progress_callback:
        progress_callback(
            {
                "phase": "chattts",
                "current": 0,
                "total": total_segments,
                "message": f"ChatTTS：0 / {total_segments} 段",
            }
        )

    for chapter_position, (chapter_record, prepared_segments) in enumerate(prepared, start=1):
        chapter_index = chapter_record["index"]
        if chapter_record.get("status") == "done" and not force:
            results.append(ChatTtsResult(chapter=chapter_index, status="skipped", output=chapter_record.get("output")))
            continue

        try:
            update_chapter(project, chapter_index, status="running", provider="chattts", error=None)
            segments = prepared_segments or []
            if not segments:
                raise RuntimeError("No text segments found")

            segment_outputs: list[Path] = []
            work_dir = project.root / "temp" / "chattts" / f"{chapter_index:04d}"
            work_dir.mkdir(parents=True, exist_ok=True)

            chapter_total_segments = len(segments)
            for segment_position, (segment_index, text) in enumerate(segments, start=1):
                wavs = chat.infer(
                    [text],
                    params_refine_text=params_refine_text,
                    params_infer_code=params_infer_code,
                    skip_refine_text=skip_refine_text,
                )
                wav_path = work_dir / f"{chapter_index:04d}_{segment_index:04d}.wav"
                mp3_path = work_dir / f"{chapter_index:04d}_{segment_index:04d}.mp3"
                write_wav(wav_path, np.asarray(wavs[0]), sample_rate=24000)
                convert_to_mp3(wav_path, mp3_path, ffmpeg=ffmpeg, bitrate="128k")
                segment_outputs.append(mp3_path)
                completed_segments += 1
                if progress_callback:
                    progress_callback(
                        {
                            "phase": "chattts",
                            "current": completed_segments,
                            "total": total_segments,
                            "chapter": chapter_index,
                            "chapter_position": chapter_position,
                            "chapter_total": len(prepared),
                            "segment": segment_position,
                            "segment_total": chapter_total_segments,
                            "message": (
                                f"ChatTTS：第 {chapter_position} / {len(prepared)} 章，"
                                f"段落 {segment_position} / {chapter_total_segments}，"
                                f"總進度 {completed_segments} / {total_segments} 段"
                            ),
                        }
                    )

            output_path = project.root / chapter_record["output"]
            create_chapter_audio(segment_outputs, output_path, ffmpeg=ffmpeg)
            update_chapter(project, chapter_index, status="done", output=str(output_path.relative_to(project.root)))
            results.append(ChatTtsResult(chapter=chapter_index, status="done", output=str(output_path)))
        except Exception as exc:
            update_chapter(project, chapter_index, status="failed", error=str(exc))
            results.append(ChatTtsResult(chapter=chapter_index, status="failed", error=str(exc)))

    return results


def split_chattts_segments(segments: list[tuple[int, str]], *, max_chars: int) -> list[tuple[int, str]]:
    """ChatTTS is much more stable with short novel chunks than long Edge-style chunks."""
    output: list[tuple[int, str]] = []
    for _, text in segments:
        for segment in split_segments(text, max_chars=max_chars):
            output.append((len(output) + 1, segment.text))
    return output


def synthesize_chattts_preview(
    *,
    text: str = DEFAULT_PREVIEW_TEXT,
    output_dir: Path,
    prompt: str = DEFAULT_CHAT_PROMPT,
    speaker_seed: int | None = None,
    source: str = "huggingface",
    custom_path: str | None = None,
    ffmpeg: str = "ffmpeg",
) -> Path:
    chat_module = import_chattts()
    chat = chat_module.Chat()
    loaded = chat.load(source=source, custom_path=custom_path, compile=False)
    if not loaded:
        raise RuntimeError("ChatTTS model failed to load.")

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    seed_label = "random" if speaker_seed is None else str(speaker_seed)
    wav_path = output_dir / f"chattts_preview_seed_{seed_label}_{stamp}.wav"
    mp3_path = output_dir / f"chattts_preview_seed_{seed_label}_{stamp}.mp3"

    params_refine_text = chat_module.Chat.RefineTextParams(prompt=prompt)
    params_infer_code = build_infer_params(chat_module, chat, speaker_seed)
    wavs = chat.infer(
        [text],
        params_refine_text=params_refine_text,
        params_infer_code=params_infer_code,
    )
    write_wav(wav_path, np.asarray(wavs[0]), sample_rate=24000)
    convert_to_mp3(wav_path, mp3_path, ffmpeg=ffmpeg, bitrate="128k")
    return mp3_path


def build_infer_params(chat_module, chat, speaker_seed: int | None):
    if speaker_seed is None:
        return chat_module.Chat.InferCodeParams()

    try:
        import torch

        torch.manual_seed(speaker_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(speaker_seed)
    except Exception:
        pass

    spk_emb = chat.sample_random_speaker()
    return chat_module.Chat.InferCodeParams(
        manual_seed=speaker_seed,
        spk_emb=spk_emb,
    )


def preload_chattts(*, source: str = "huggingface", custom_path: str | None = None) -> str:
    chat_module = import_chattts()
    chat = chat_module.Chat()
    loaded = chat.load(source=source, custom_path=custom_path, compile=False)
    if not loaded:
        raise RuntimeError("ChatTTS model failed to load.")
    return "ChatTTS model loaded successfully."


def import_chattts():
    try:
        import ChatTTS

        return ChatTTS
    except ImportError as exc:
        raise RuntimeError(
            "ChatTTS is not installed. Install it with: python -m pip install -r requirements-chattts.txt"
        ) from exc


def write_wav(path: Path, samples: np.ndarray, *, sample_rate: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = np.squeeze(samples)
    if samples.ndim != 1:
        raise ValueError(f"Expected mono audio, got shape {samples.shape}")

    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767).astype(np.int16)

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path
