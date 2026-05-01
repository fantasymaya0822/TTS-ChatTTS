from __future__ import annotations

import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests


API_VERSION = "2024-04-01"
OUTPUT_FORMAT = "audio-16khz-128kbitrate-mono-mp3"


@dataclass(frozen=True)
class BatchJob:
    id: str
    status: str
    result_url: str | None = None


class AzureBatchTtsClient:
    def __init__(self, *, speech_key: str, region: str) -> None:
        self.speech_key = speech_key
        self.region = region
        self.base_url = f"https://{region}.api.cognitive.microsoft.com/texttospeech/batchsyntheses"
        self.voice_url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list"

    def list_voices(self) -> list[dict]:
        response = requests.get(self.voice_url, headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json()

    def submit_ssml_job(
        self,
        *,
        ssml_inputs: list[str],
        description: str,
        concatenate_result: bool = False,
    ) -> BatchJob:
        job_id = make_job_id()
        payload = {
            "description": description,
            "inputKind": "SSML",
            "inputs": [{"content": ssml} for ssml in ssml_inputs],
            "properties": {
                "outputFormat": OUTPUT_FORMAT,
                "wordBoundaryEnabled": False,
                "sentenceBoundaryEnabled": False,
                "concatenateResult": concatenate_result,
                "decompressOutputFiles": False,
                "timeToLiveInHours": 168,
            },
        }
        response = requests.put(
            self._job_url(job_id),
            headers=self._headers(),
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
        return BatchJob(id=body["id"], status=body["status"], result_url=None)

    def get_job(self, job_id: str) -> BatchJob:
        response = requests.get(self._job_url(job_id), headers=self._headers(), timeout=30)
        response.raise_for_status()
        body = response.json()
        return BatchJob(
            id=body["id"],
            status=body["status"],
            result_url=body.get("outputs", {}).get("result"),
        )

    def wait_for_job(self, job_id: str, *, poll_seconds: int = 15, timeout_seconds: int = 60 * 60 * 12) -> BatchJob:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            job = self.get_job(job_id)
            if job.status in {"Succeeded", "Failed"}:
                return job
            time.sleep(poll_seconds)
        raise TimeoutError(f"Timed out waiting for Azure batch synthesis job {job_id}")

    def download_result_zip(self, *, result_url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(result_url, headers=self._headers(), timeout=300)
        response.raise_for_status()
        destination.write_bytes(response.content)
        return destination

    def extract_audio_files(self, *, zip_path: Path, destination_dir: Path) -> list[Path]:
        destination_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(destination_dir)
        return sorted(
            path
            for path in destination_dir.iterdir()
            if path.suffix.lower() in {".mp3", ".wav", ".ogg"}
        )

    def _job_url(self, job_id: str) -> str:
        return f"{self.base_url}/{job_id}?api-version={API_VERSION}"

    def _headers(self) -> dict[str, str]:
        return {
            "Ocp-Apim-Subscription-Key": self.speech_key,
            "Content-Type": "application/json",
        }


def make_job_id() -> str:
    return f"novel-{uuid.uuid4().hex[:24]}"
