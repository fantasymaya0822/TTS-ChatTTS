from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from novel_tts.audio_merge import create_chapter_audio, create_full_book_audio
from novel_tts.audio_merge import resolve_ffmpeg
from novel_tts.azure_batch import AzureBatchTtsClient
from novel_tts.chattts_provider import (
    DEFAULT_CHAT_PROMPT,
    DEFAULT_PREVIEW_TEXT,
    preload_chattts,
    synthesize_chattts_preview,
    synthesize_project_chattts,
)
from novel_tts.cli_helpers import read_chapter_ssml, select_chapters
from novel_tts.edge_provider import DEFAULT_EDGE_VOICE, list_edge_voices_sync, synthesize_project_edge
from novel_tts.project import open_project, update_chapter
from novel_tts.workflow import prepare_project, summary_json


def prepare(args: argparse.Namespace) -> int:
    source = Path(args.input).expanduser().resolve()
    output_root = Path(args.out).expanduser().resolve()

    result = prepare_project(
        source=source,
        output_root=output_root,
        voice=args.voice,
        locale=args.locale,
        rate=args.rate,
        max_segment_chars=args.max_segment_chars,
    )
    print(summary_json(result.summary))
    return 0


def synthesize(args: argparse.Namespace) -> int:
    project = open_project(Path(args.project))
    manifest = project.load_manifest()
    speech_key = args.key or os.getenv("AZURE_SPEECH_KEY")
    region = args.region or os.getenv("AZURE_SPEECH_REGION") or os.getenv("AZURE_REGION")

    if not speech_key:
        raise SystemExit("Missing Azure Speech key. Pass --key or set AZURE_SPEECH_KEY.")
    if not region:
        raise SystemExit("Missing Azure Speech region. Pass --region or set AZURE_SPEECH_REGION.")

    client = AzureBatchTtsClient(speech_key=speech_key, region=region)
    chapters = manifest["chapters"]
    selected = select_chapters(chapters, args.chapter)

    results: list[dict] = []
    for chapter in selected:
        chapter_index = chapter["index"]
        if chapter.get("status") == "done" and not args.force:
            results.append({"chapter": chapter_index, "status": "skipped", "output": chapter.get("output")})
            continue

        ssml_inputs = read_chapter_ssml(project.root, chapter_index)
        if not ssml_inputs:
            update_chapter(project, chapter_index, status="failed", error="No SSML files found")
            results.append({"chapter": chapter_index, "status": "failed", "error": "No SSML files found"})
            continue

        update_chapter(project, chapter_index, status="submitting", error=None)
        job = client.submit_ssml_job(
            ssml_inputs=ssml_inputs,
            description=f"{project.root.name} chapter {chapter_index:04d}",
            concatenate_result=True,
        )
        update_chapter(project, chapter_index, status="running", azure_job_id=job.id)

        if args.submit_only:
            results.append({"chapter": chapter_index, "status": "submitted", "job_id": job.id})
            continue

        final_job = client.wait_for_job(job.id, poll_seconds=args.poll_seconds)
        update_chapter(
            project,
            chapter_index,
            status=final_job.status.lower(),
            azure_job_id=final_job.id,
            azure_result_url=final_job.result_url,
        )

        if final_job.status != "Succeeded" or not final_job.result_url:
            results.append({"chapter": chapter_index, "status": final_job.status, "job_id": final_job.id})
            continue

        chapter_work_dir = project.root / "temp" / "downloads" / f"{chapter_index:04d}"
        zip_path = chapter_work_dir / "results.zip"
        client.download_result_zip(result_url=final_job.result_url, destination=zip_path)
        audio_files = client.extract_audio_files(zip_path=zip_path, destination_dir=chapter_work_dir / "extracted")

        output_path = project.root / chapter["output"]
        create_chapter_audio(audio_files, output_path, ffmpeg=args.ffmpeg)
        update_chapter(project, chapter_index, status="done", output=str(output_path.relative_to(project.root)))
        results.append({"chapter": chapter_index, "status": "done", "output": str(output_path)})

    print(json.dumps({"project": str(project.root), "results": results}, ensure_ascii=False, indent=2))
    return 0


def poll(args: argparse.Namespace) -> int:
    project = open_project(Path(args.project))
    speech_key = args.key or os.getenv("AZURE_SPEECH_KEY")
    region = args.region or os.getenv("AZURE_SPEECH_REGION") or os.getenv("AZURE_REGION")

    if not speech_key:
        raise SystemExit("Missing Azure Speech key. Pass --key or set AZURE_SPEECH_KEY.")
    if not region:
        raise SystemExit("Missing Azure Speech region. Pass --region or set AZURE_SPEECH_REGION.")

    client = AzureBatchTtsClient(speech_key=speech_key, region=region)
    manifest = project.load_manifest()
    results = []

    for chapter in manifest["chapters"]:
        job_id = chapter.get("azure_job_id")
        if not job_id or chapter.get("status") == "done":
            continue
        job = client.get_job(job_id)
        update_chapter(
            project,
            chapter["index"],
            status=job.status.lower(),
            azure_result_url=job.result_url,
        )
        results.append({"chapter": chapter["index"], "job_id": job.id, "status": job.status})

    print(json.dumps({"project": str(project.root), "results": results}, ensure_ascii=False, indent=2))
    return 0


def voices(args: argparse.Namespace) -> int:
    speech_key = args.key or os.getenv("AZURE_SPEECH_KEY")
    region = args.region or os.getenv("AZURE_SPEECH_REGION") or os.getenv("AZURE_REGION")

    if not speech_key:
        raise SystemExit("Missing Azure Speech key. Pass --key or set AZURE_SPEECH_KEY.")
    if not region:
        raise SystemExit("Missing Azure Speech region. Pass --region or set AZURE_SPEECH_REGION.")

    client = AzureBatchTtsClient(speech_key=speech_key, region=region)
    all_voices = client.list_voices()
    filtered = [
        voice
        for voice in all_voices
        if not args.locale or voice.get("Locale", "").lower() == args.locale.lower()
    ]
    rows = [
        {
            "name": voice.get("ShortName"),
            "locale": voice.get("Locale"),
            "gender": voice.get("Gender"),
            "display_name": voice.get("DisplayName"),
            "local_name": voice.get("LocalName"),
        }
        for voice in filtered
    ]
    print(json.dumps({"count": len(rows), "voices": rows}, ensure_ascii=False, indent=2))
    return 0


def edge_voices(args: argparse.Namespace) -> int:
    all_voices = list_edge_voices_sync(args.locale)
    rows = [
        {
            "name": voice.get("ShortName"),
            "locale": voice.get("Locale"),
            "gender": voice.get("Gender"),
            "display_name": voice.get("FriendlyName") or voice.get("DisplayName"),
        }
        for voice in all_voices
    ]
    print(json.dumps({"count": len(rows), "voices": rows}, ensure_ascii=False, indent=2))
    return 0


def edge_synthesize(args: argparse.Namespace) -> int:
    project = open_project(Path(args.project))
    results = synthesize_project_edge(
        project=project,
        voice=args.voice,
        rate=args.rate,
        chapter=args.chapter,
        force=args.force,
        ffmpeg=args.ffmpeg,
    )
    print(
        json.dumps(
            {
                "project": str(project.root),
                "results": [result.__dict__ for result in results],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def chattts_synthesize(args: argparse.Namespace) -> int:
    project = open_project(Path(args.project))
    try:
        results = synthesize_project_chattts(
            project=project,
            chapter=args.chapter,
            force=args.force,
            prompt=args.prompt,
            skip_refine_text=args.skip_refine_text,
            speaker_seed=args.speaker_seed,
            source=args.source,
            custom_path=args.custom_path,
            ffmpeg=args.ffmpeg,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        json.dumps(
            {
                "project": str(project.root),
                "results": [result.__dict__ for result in results],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def chattts_preload(args: argparse.Namespace) -> int:
    try:
        print(preload_chattts(source=args.source, custom_path=args.custom_path))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


def chattts_preview(args: argparse.Namespace) -> int:
    try:
        output = synthesize_chattts_preview(
            text=args.text,
            output_dir=Path(args.out).expanduser().resolve(),
            prompt=args.prompt,
            speaker_seed=args.speaker_seed,
            source=args.source,
            custom_path=args.custom_path,
            ffmpeg=args.ffmpeg,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({"output": str(output)}, ensure_ascii=False, indent=2))
    return 0


def merge_full(args: argparse.Namespace) -> int:
    project = open_project(Path(args.project))
    output = create_full_book_audio(project.root, ffmpeg=args.ffmpeg)
    print(json.dumps({"project": str(project.root), "output": str(output)}, ensure_ascii=False, indent=2))
    return 0


def doctor(args: argparse.Namespace) -> int:
    ffmpeg_path = None
    try:
        ffmpeg_path = resolve_ffmpeg(args.ffmpeg)
    except RuntimeError:
        ffmpeg_path = None

    checks = {
        "ffmpeg": bool(ffmpeg_path),
        "ffmpeg_path": ffmpeg_path,
        "azure_speech_key": bool(os.getenv("AZURE_SPEECH_KEY")),
        "azure_speech_region": bool(os.getenv("AZURE_SPEECH_REGION") or os.getenv("AZURE_REGION")),
    }
    checks["ready_for_prepare"] = True
    checks["ready_for_edge_synthesize"] = True
    checks["ready_for_azure_synthesize"] = checks["azure_speech_key"] and checks["azure_speech_region"]
    checks["ready_for_audio_merge"] = checks["ffmpeg"]
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="novel-tts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="prepare a novel project")
    prepare_parser.add_argument("input", help="input .txt novel path")
    prepare_parser.add_argument("--out", default="output", help="output root directory")
    prepare_parser.add_argument("--voice", default=DEFAULT_EDGE_VOICE, help="TTS voice name")
    prepare_parser.add_argument("--locale", default="zh-TW", help="SSML locale")
    prepare_parser.add_argument("--rate", default="+10%", help="SSML prosody rate, for example +10%")
    prepare_parser.add_argument(
        "--max-segment-chars",
        type=int,
        default=4500,
        help="maximum plain-text characters per segment before SSML wrapping",
    )
    prepare_parser.set_defaults(func=prepare)

    synthesize_parser = subparsers.add_parser("synthesize", help="submit prepared chapters to Azure Batch TTS")
    synthesize_parser.add_argument("project", help="project folder or project.json path")
    synthesize_parser.add_argument("--key", help="Azure Speech key. Can also use AZURE_SPEECH_KEY.")
    synthesize_parser.add_argument("--region", help="Azure Speech region. Can also use AZURE_SPEECH_REGION.")
    synthesize_parser.add_argument("--chapter", type=int, help="only synthesize one chapter index")
    synthesize_parser.add_argument("--submit-only", action="store_true", help="submit jobs without waiting/downloading")
    synthesize_parser.add_argument("--force", action="store_true", help="re-submit chapters even if already done")
    synthesize_parser.add_argument("--poll-seconds", type=int, default=15, help="seconds between Azure status checks")
    synthesize_parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable path")
    synthesize_parser.set_defaults(func=synthesize)

    poll_parser = subparsers.add_parser("poll", help="refresh Azure job statuses for a project")
    poll_parser.add_argument("project", help="project folder or project.json path")
    poll_parser.add_argument("--key", help="Azure Speech key. Can also use AZURE_SPEECH_KEY.")
    poll_parser.add_argument("--region", help="Azure Speech region. Can also use AZURE_SPEECH_REGION.")
    poll_parser.set_defaults(func=poll)

    voices_parser = subparsers.add_parser("voices", help="list Azure TTS voices")
    voices_parser.add_argument("--key", help="Azure Speech key. Can also use AZURE_SPEECH_KEY.")
    voices_parser.add_argument("--region", help="Azure Speech region. Can also use AZURE_SPEECH_REGION.")
    voices_parser.add_argument("--locale", default="zh-TW", help="filter by locale, for example zh-TW")
    voices_parser.set_defaults(func=voices)

    edge_voices_parser = subparsers.add_parser("edge-voices", help="list Microsoft Edge TTS voices")
    edge_voices_parser.add_argument("--locale", default="zh-TW", help="filter by locale, for example zh-TW")
    edge_voices_parser.set_defaults(func=edge_voices)

    edge_synthesize_parser = subparsers.add_parser("edge-synthesize", help="synthesize prepared chapters with Edge TTS")
    edge_synthesize_parser.add_argument("project", help="project folder or project.json path")
    edge_synthesize_parser.add_argument("--voice", default=DEFAULT_EDGE_VOICE, help="Edge voice name")
    edge_synthesize_parser.add_argument("--rate", default="+10%", help="speaking rate, for example +10%")
    edge_synthesize_parser.add_argument("--chapter", type=int, help="only synthesize one chapter index")
    edge_synthesize_parser.add_argument("--force", action="store_true", help="re-submit chapters even if already done")
    edge_synthesize_parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable path")
    edge_synthesize_parser.set_defaults(func=edge_synthesize)

    chattts_parser = subparsers.add_parser("chattts-synthesize", help="synthesize prepared chapters with local ChatTTS")
    chattts_parser.add_argument("project", help="project folder or project.json path")
    chattts_parser.add_argument("--chapter", type=int, help="only synthesize one chapter index")
    chattts_parser.add_argument("--force", action="store_true", help="re-submit chapters even if already done")
    chattts_parser.add_argument("--prompt", default=DEFAULT_CHAT_PROMPT, help="ChatTTS refine prompt")
    chattts_parser.add_argument("--skip-refine-text", action="store_true", help="skip ChatTTS text refinement")
    chattts_parser.add_argument("--speaker-seed", type=int, help="fixed ChatTTS speaker seed")
    chattts_parser.add_argument("--source", default="huggingface", choices=["huggingface", "local", "custom"])
    chattts_parser.add_argument("--custom-path", help="custom local ChatTTS model path")
    chattts_parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable path")
    chattts_parser.set_defaults(func=chattts_synthesize)

    chattts_preload_parser = subparsers.add_parser("chattts-preload", help="download/load the local ChatTTS model")
    chattts_preload_parser.add_argument("--source", default="huggingface", choices=["huggingface", "local", "custom"])
    chattts_preload_parser.add_argument("--custom-path", help="custom local ChatTTS model path")
    chattts_preload_parser.set_defaults(func=chattts_preload)

    chattts_preview_parser = subparsers.add_parser("chattts-preview", help="create a short ChatTTS preview MP3")
    chattts_preview_parser.add_argument("--text", default=DEFAULT_PREVIEW_TEXT, help="preview text")
    chattts_preview_parser.add_argument("--out", default="output/previews", help="preview output folder")
    chattts_preview_parser.add_argument("--prompt", default=DEFAULT_CHAT_PROMPT, help="ChatTTS refine prompt")
    chattts_preview_parser.add_argument("--speaker-seed", type=int, help="fixed ChatTTS speaker seed")
    chattts_preview_parser.add_argument("--source", default="huggingface", choices=["huggingface", "local", "custom"])
    chattts_preview_parser.add_argument("--custom-path", help="custom local ChatTTS model path")
    chattts_preview_parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable path")
    chattts_preview_parser.set_defaults(func=chattts_preview)

    merge_full_parser = subparsers.add_parser("merge-full", help="merge chapter MP3 files into one full-book MP3")
    merge_full_parser.add_argument("project", help="project folder or project.json path")
    merge_full_parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable path")
    merge_full_parser.set_defaults(func=merge_full)

    doctor_parser = subparsers.add_parser("doctor", help="check local environment")
    doctor_parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable path")
    doctor_parser.set_defaults(func=doctor)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
