from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def resolve_ffmpeg(ffmpeg: str = "ffmpeg") -> str:
    found = shutil.which(ffmpeg)
    if found:
        return found

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError(
            "FFmpeg was not found. Install FFmpeg or install imageio-ffmpeg with requirements.txt."
        ) from exc


def create_chapter_audio(audio_files: list[Path], output_path: Path, *, ffmpeg: str = "ffmpeg") -> Path:
    if not audio_files:
        raise ValueError("No audio files to merge")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if len(audio_files) == 1:
        shutil.copyfile(audio_files[0], output_path)
        return output_path

    concat_file = output_path.with_suffix(".concat.txt")
    concat_file.write_text(
        "\n".join(f"file '{path.resolve().as_posix()}'" for path in audio_files),
        encoding="utf-8",
    )

    ffmpeg_exe = resolve_ffmpeg(ffmpeg)
    command = [
        ffmpeg_exe,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "ffmpeg failed to merge audio files")

    concat_file.unlink(missing_ok=True)
    return output_path


def create_full_book_audio(project_root: Path, *, ffmpeg: str = "ffmpeg") -> Path:
    chapters_dir = project_root / "chapters"
    audio_files = sorted(path for path in chapters_dir.glob("*.mp3") if path.is_file())
    if not audio_files:
        raise ValueError(f"No chapter MP3 files found under {chapters_dir}")

    output_path = project_root / "full" / f"{project_root.name}_full.mp3"
    return create_chapter_audio(audio_files, output_path, ffmpeg=ffmpeg)


def convert_to_mp3(input_path: Path, output_path: Path, *, ffmpeg: str = "ffmpeg", bitrate: str = "128k") -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        resolve_ffmpeg(ffmpeg),
        "-y",
        "-i",
        str(input_path),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "ffmpeg failed to convert audio")
    return output_path
