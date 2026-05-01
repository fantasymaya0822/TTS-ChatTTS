from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from novel_tts.chapter_splitter import Chapter


@dataclass(frozen=True)
class Project:
    root: Path

    @property
    def manifest_path(self) -> Path:
        return self.root / "project.json"

    def load_manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def save_manifest(self, manifest: dict) -> None:
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def create_project(
    *,
    source_path: Path,
    output_root: Path,
    encoding: str,
    chapters: list[Chapter],
    voice: str,
    locale: str,
    rate: str,
) -> Project:
    project_name = safe_name(source_path.stem)
    root = unique_project_root(output_root / project_name)

    for path in [
        root / "chapters",
        root / "temp" / "ssml",
        root / "temp" / "segments",
        root / "temp" / "downloads",
        root / "full",
    ]:
        path.mkdir(parents=True, exist_ok=True)

    chapter_records = [
        {
            "index": chapter.index,
            "title": chapter.title,
            "characters": chapter.char_count,
            "status": "pending",
            "output": f"chapters/{chapter.index:04d}_{safe_name(chapter.title)}.mp3",
        }
        for chapter in chapters
    ]

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source_path),
        "encoding": encoding,
        "settings": {
            "voice": voice,
            "locale": locale,
            "rate": rate,
            "output_format": "audio-16khz-128kbitrate-mono-mp3",
        },
        "totals": {
            "chapters": len(chapters),
            "characters": sum(chapter.char_count for chapter in chapters),
        },
        "chapters": chapter_records,
    }
    (root / "project.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return Project(root=root)


def open_project(path: Path) -> Project:
    root = path.expanduser().resolve()
    if root.is_file():
        root = root.parent
    manifest_path = root / "project.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"project.json not found under {root}")
    return Project(root=root)


def update_chapter(project: Project, chapter_index: int, **updates: object) -> dict:
    manifest = project.load_manifest()
    for chapter in manifest["chapters"]:
        if chapter["index"] == chapter_index:
            chapter.update(updates)
            chapter["updated_at"] = datetime.now(timezone.utc).isoformat()
            project.save_manifest(manifest)
            return chapter
    raise KeyError(f"Chapter {chapter_index} not found")


def safe_name(value: str, fallback: str = "novel") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:80] or fallback


def unique_project_root(base: Path) -> Path:
    if not base.exists():
        return base
    for i in range(2, 1000):
        candidate = base.with_name(f"{base.name}_{i}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not create a unique project folder for {base}")
