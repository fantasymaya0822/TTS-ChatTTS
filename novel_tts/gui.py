from __future__ import annotations

import os
import json
import sys
import tempfile
import time
import traceback
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSettings, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from novel_tts.edge_provider import DEFAULT_EDGE_VOICE, list_edge_voices_sync, synthesize_project_edge
from novel_tts.audio_merge import create_full_book_audio
from novel_tts.chattts_provider import (
    DEFAULT_CHAT_PROMPT,
    DEFAULT_PREVIEW_TEXT,
    synthesize_chattts_preview,
    synthesize_project_chattts,
)
from novel_tts.fish_provider import (
    DEFAULT_FISH_MAX_CHARS,
    DEFAULT_FISH_MAX_NEW_TOKENS,
    DEFAULT_FISH_SERVER_URL,
    DEFAULT_FISH_XPU_SERVER_URL,
    synthesize_project_fish,
)
from novel_tts.i18n import t
from novel_tts.project import open_project as load_project
from novel_tts.workflow import prepare_project, summary_json


class WorkerSignals(QObject):
    started = Signal(str)
    progress = Signal(object)
    finished = Signal(object)
    failed = Signal(str)
    completed = Signal()


class Worker(QRunnable):
    def __init__(self, title: str, fn, *args, progress_arg: str | None = None, **kwargs) -> None:
        super().__init__()
        self.title = title
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.progress_arg = progress_arg
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        self.signals.started.emit(self.title)
        try:
            if self.progress_arg:
                self.kwargs[self.progress_arg] = self.signals.progress.emit
            self.signals.finished.emit(self.fn(*self.args, **self.kwargs))
        except Exception:
            self.signals.failed.emit(traceback.format_exc())
        finally:
            self.signals.completed.emit()


def run_chattts_preview_isolated(
    *,
    text: str,
    output_dir: Path,
    prompt: str,
    speaker_seed: int | None,
    source: str = "huggingface",
    ffmpeg: str = "ffmpeg",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    request = {
        "text": text,
        "output_dir": str(output_dir),
        "prompt": prompt,
        "speaker_seed": speaker_seed,
        "source": source,
        "ffmpeg": ffmpeg,
    }
    request_fd, request_name = tempfile.mkstemp(prefix="chattts_preview_", suffix=".json")
    result_fd, result_name = tempfile.mkstemp(prefix="chattts_preview_result_", suffix=".json")
    os.close(request_fd)
    os.close(result_fd)
    request_path = Path(request_name)
    result_path = Path(result_name)
    try:
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command.extend(["-m", "novel_tts.gui"])
        command.extend(["--chattts-preview-worker", str(request_path), str(result_path)])

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "").strip()
            if not details:
                details = f"ChatTTS preview worker exited with code {completed.returncode}."
            raise RuntimeError(details)
        if not result_path.exists():
            raise RuntimeError("ChatTTS preview worker did not write a result file.")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("error"):
            raise RuntimeError(str(result["error"]))
        return Path(result["output"])
    finally:
        for path in [request_path, result_path]:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def run_chattts_preview_worker(request_path: Path, result_path: Path) -> int:
    try:
        request = json.loads(request_path.read_text(encoding="utf-8-sig"))
        output = synthesize_chattts_preview(
            text=request["text"],
            output_dir=Path(request["output_dir"]),
            prompt=request["prompt"],
            speaker_seed=request["speaker_seed"],
            source=request["source"],
            ffmpeg=request["ffmpeg"],
        )
        result_path.write_text(json.dumps({"output": str(output)}, ensure_ascii=False), encoding="utf-8")
        return 0
    except Exception:
        result_path.write_text(json.dumps({"error": traceback.format_exc()}, ensure_ascii=False), encoding="utf-8")
        return 1


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(t("window_title"))
        self.resize(980, 720)
        self.thread_pool = QThreadPool.globalInstance()
        self.settings = QSettings("NovelTTS", "AzureNovelTTS")
        self.project_path: Path | None = None
        self.voices: list[dict] = []
        self.active_workers: list[Worker] = []
        self.progress_started_at: float | None = None

        from PySide6.QtWidgets import QLineEdit

        self.source_edit = QLineEdit()
        self.output_edit = QLineEdit(str(Path.cwd() / "output"))
        self.locale_combo = QComboBox()
        self.locale_combo.addItems(["zh-TW", "zh-CN", "ja-JP", "en-US"])
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Edge TTS", "edge")
        self.provider_combo.addItem("ChatTTS 本地模型", "chattts")
        self.provider_combo.addItem("Fish Speech API", "fish")
        self.voice_combo = QComboBox()
        self.voice_combo.setEditable(True)
        self.voice_combo.addItem(DEFAULT_EDGE_VOICE, DEFAULT_EDGE_VOICE)
        self.rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.rate_slider.setRange(-50, 100)
        self.rate_slider.setValue(10)
        self.rate_label = QLabel("+10%")
        self.segment_spin = QSpinBox()
        self.segment_spin.setRange(1000, 12000)
        self.segment_spin.setSingleStep(500)
        self.segment_spin.setValue(4500)
        self.chattts_prompt_edit = QLineEdit(DEFAULT_CHAT_PROMPT)
        self.chattts_seed_spin = QSpinBox()
        self.chattts_seed_spin.setRange(0, 2_147_483_647)
        self.chattts_seed_spin.setSpecialValueText("隨機")
        self.chattts_seed_spin.setValue(42)
        self.chattts_seed_combo = QComboBox()
        self.chattts_seed_combo.setEditable(True)
        self.chattts_preview_text_edit = QLineEdit(DEFAULT_PREVIEW_TEXT)
        self.fish_url_edit = QLineEdit(DEFAULT_FISH_SERVER_URL)
        self.fish_xpu_url_button = QPushButton("Use local XPU server")
        self.fish_reference_id_edit = QLineEdit()
        self.fish_api_key_edit = QLineEdit()
        self.fish_seed_spin = QSpinBox()
        self.fish_seed_spin.setRange(0, 2_147_483_647)
        self.fish_seed_spin.setSpecialValueText("隨機")
        self.fish_chunk_spin = QSpinBox()
        self.fish_chunk_spin.setRange(100, 2000)
        self.fish_chunk_spin.setSingleStep(100)
        self.fish_chunk_spin.setValue(DEFAULT_FISH_MAX_CHARS)
        self.fish_api_chunk_spin = QSpinBox()
        self.fish_api_chunk_spin.setRange(100, 1000)
        self.fish_api_chunk_spin.setSingleStep(50)
        self.fish_api_chunk_spin.setValue(300)
        self.fish_max_new_tokens_spin = QSpinBox()
        self.fish_max_new_tokens_spin.setRange(1, 2048)
        self.fish_max_new_tokens_spin.setSingleStep(8)
        self.fish_max_new_tokens_spin.setValue(DEFAULT_FISH_MAX_NEW_TOKENS)
        self.chapter_spin = QSpinBox()
        self.chapter_spin.setRange(0, 9999)
        self.chapter_spin.setSpecialValueText(t("all"))
        self.force_check = QCheckBox(t("force"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.progress_label = QLabel("待命")
        self.progress_label.setVisible(False)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log.setFont(QFont("Consolas", 10))
        self.chapter_table = QTableWidget(0, 5)
        self.chapter_table.setHorizontalHeaderLabels(
            [t("table_index"), t("table_title"), t("table_chars"), t("table_status"), t("table_output")]
        )
        self.chapter_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.chapter_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.chapter_table.verticalHeader().setVisible(False)

        self.prepare_button = QPushButton("1. 匯入 TXT / 切章節")
        self.voices_button = QPushButton("載入 Edge 語音")
        self.synthesize_button = QPushButton("2. 開始轉檔")
        self.open_project_button = QPushButton("開啟既有專案")
        self.merge_full_button = QPushButton("3. 合併整本")
        self.preview_voice_button = QPushButton("試聽 ChatTTS")
        self.save_seed_button = QPushButton(t("save_seed"))
        self.refresh_button = QPushButton("更新列表")
        self.open_folder_button = QPushButton("開啟輸出資料夾")
        self.prepare_button.setToolTip("第一次使用：選 TXT 後按這裡，程式會建立專案資料夾並切出章節/段落。")
        self.open_project_button.setToolTip("再次使用：打開之前已經匯入過的專案資料夾。")
        self.synthesize_button.setToolTip("把目前專案的章節轉成 MP3。")
        self.merge_full_button.setToolTip("把各章 MP3 合併成一本完整 MP3。")

        self._build_ui()
        self._connect()
        self._load_settings()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        file_group = QGroupBox(t("novel_file"))
        file_layout = QGridLayout(file_group)
        file_layout.addWidget(QLabel("TXT"), 0, 0)
        file_layout.addWidget(self.source_edit, 0, 1)
        source_button = QPushButton(t("browse"))
        source_button.clicked.connect(self.choose_source)
        file_layout.addWidget(source_button, 0, 2)
        file_layout.addWidget(QLabel(t("output_folder")), 1, 0)
        file_layout.addWidget(self.output_edit, 1, 1)
        output_button = QPushButton(t("browse"))
        output_button.clicked.connect(self.choose_output)
        file_layout.addWidget(output_button, 1, 2)
        root.addWidget(file_group)

        tabs = QTabWidget()
        tabs.addTab(self.build_global_tab(), t("global_options"))
        tabs.addTab(self.build_edge_tab(), t("edge_options"))
        tabs.addTab(self.build_chattts_tab(), t("chattts_options"))
        tabs.addTab(self.build_fish_tab(), "Fish Speech")
        root.addWidget(tabs)

        button_row = QHBoxLayout()
        button_row.addWidget(self.prepare_button)
        button_row.addWidget(self.open_project_button)
        button_row.addWidget(self.synthesize_button)
        button_row.addWidget(self.merge_full_button)
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.open_folder_button)
        button_row.addStretch(1)
        root.addLayout(button_row)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)
        root.addWidget(self.progress_label)
        root.addWidget(self.progress)
        root.addWidget(self.chapter_table, 2)
        root.addWidget(self.log, 1)
        self.setCentralWidget(central)

    def build_global_tab(self) -> QWidget:
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        layout.addRow(t("provider"), self.provider_combo)
        layout.addRow(t("rate"), self.rate_slider)
        layout.addRow("", self.rate_label)
        layout.addRow(t("segment_chars"), self.segment_spin)
        layout.addRow(t("chapter"), self.chapter_spin)
        layout.addRow("", self.force_check)
        return tab

    def build_edge_tab(self) -> QWidget:
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        layout.addRow(t("locale"), self.locale_combo)
        layout.addRow(t("voice"), self.voice_combo)
        layout.addRow("", self.voices_button)
        return tab

    def build_chattts_tab(self) -> QWidget:
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        layout.addRow(t("chattts_seed"), self.chattts_seed_spin)
        layout.addRow(t("seed_select"), self.chattts_seed_combo)

        seed_buttons = QHBoxLayout()
        seed_buttons.addWidget(self.save_seed_button)
        seed_buttons.addStretch(1)
        layout.addRow("", seed_buttons)

        layout.addRow(t("chattts_prompt"), self.chattts_prompt_edit)
        layout.addRow(t("chattts_preview_text"), self.chattts_preview_text_edit)
        layout.addRow("", self.preview_voice_button)
        return tab

    def build_fish_tab(self) -> QWidget:
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        layout.addRow("Server URL", self.fish_url_edit)
        layout.addRow("", self.fish_xpu_url_button)
        layout.addRow("Reference ID", self.fish_reference_id_edit)
        layout.addRow("API Key", self.fish_api_key_edit)
        layout.addRow("Seed", self.fish_seed_spin)
        layout.addRow("本機切段字數", self.fish_chunk_spin)
        layout.addRow("API chunk_length", self.fish_api_chunk_spin)
        layout.addRow("Max new tokens", self.fish_max_new_tokens_spin)
        return tab

    def _connect(self) -> None:
        self.rate_slider.valueChanged.connect(self.update_rate_label)
        self.prepare_button.clicked.connect(self.prepare_project)
        self.voices_button.clicked.connect(self.load_voices)
        self.synthesize_button.clicked.connect(self.run_synthesize)
        self.preview_voice_button.clicked.connect(self.preview_chattts_voice)
        self.fish_xpu_url_button.clicked.connect(self.use_fish_xpu_server)
        self.save_seed_button.clicked.connect(self.save_current_seed)
        self.chattts_seed_combo.currentTextChanged.connect(self.on_seed_combo_changed)
        self.open_project_button.clicked.connect(self.open_project)
        self.merge_full_button.clicked.connect(self.merge_full_book)
        self.refresh_button.clicked.connect(self.refresh_chapter_table)
        self.open_folder_button.clicked.connect(self.open_output_folder)
        self.chapter_table.itemSelectionChanged.connect(self.on_table_selection_changed)

    def _load_settings(self) -> None:
        self.output_edit.setText(str(self.settings.value("paths/output", self.output_edit.text())))
        self.locale_combo.setCurrentText(str(self.settings.value("edge/locale", "zh-TW")))
        self.voice_combo.setCurrentText(str(self.settings.value("edge/voice", DEFAULT_EDGE_VOICE)))
        self.provider_combo.setCurrentIndex(int(self.settings.value("provider/index", 0)))
        self.chattts_prompt_edit.setText(str(self.settings.value("chattts/prompt", DEFAULT_CHAT_PROMPT)))
        self.chattts_seed_spin.setValue(int(self.settings.value("chattts/speaker_seed", 42)))
        self.chattts_preview_text_edit.setText(
            str(self.settings.value("chattts/preview_text", DEFAULT_PREVIEW_TEXT))
        )
        self.fish_url_edit.setText(str(self.settings.value("fish/url", DEFAULT_FISH_SERVER_URL)))
        self.fish_reference_id_edit.setText(str(self.settings.value("fish/reference_id", "")))
        self.fish_api_key_edit.setText(str(self.settings.value("fish/api_key", "")))
        self.fish_seed_spin.setValue(int(self.settings.value("fish/seed", 0)))
        self.fish_chunk_spin.setValue(int(self.settings.value("fish/max_chunk_chars", DEFAULT_FISH_MAX_CHARS)))
        self.fish_api_chunk_spin.setValue(int(self.settings.value("fish/api_chunk_length", 300)))
        self.fish_max_new_tokens_spin.setValue(
            int(self.settings.value("fish/max_new_tokens", DEFAULT_FISH_MAX_NEW_TOKENS))
        )
        self.load_saved_seeds()

    def _save_settings(self) -> None:
        self.settings.setValue("paths/output", self.output_edit.text().strip())
        self.settings.setValue("edge/locale", self.locale_combo.currentText())
        self.settings.setValue("edge/voice", self.selected_voice())
        self.settings.setValue("provider/index", self.provider_combo.currentIndex())
        self.settings.setValue("chattts/prompt", self.chattts_prompt_edit.text().strip())
        self.settings.setValue("chattts/speaker_seed", self.chattts_seed_spin.value())
        self.settings.setValue("chattts/preview_text", self.chattts_preview_text_edit.text().strip())
        self.settings.setValue("chattts/saved_seeds", ",".join(self.saved_seed_values()))
        self.settings.setValue("fish/url", self.fish_url_edit.text().strip())
        self.settings.setValue("fish/reference_id", self.fish_reference_id_edit.text().strip())
        self.settings.setValue("fish/api_key", self.fish_api_key_edit.text().strip())
        self.settings.setValue("fish/seed", self.fish_seed_spin.value())
        self.settings.setValue("fish/max_chunk_chars", self.fish_chunk_spin.value())
        self.settings.setValue("fish/api_chunk_length", self.fish_api_chunk_spin.value())
        self.settings.setValue("fish/max_new_tokens", self.fish_max_new_tokens_spin.value())

    def use_fish_xpu_server(self) -> None:
        self.fish_url_edit.setText(DEFAULT_FISH_XPU_SERVER_URL)
        self._save_settings()
        self.append_log(f"Fish Speech Server URL: {DEFAULT_FISH_XPU_SERVER_URL}")

    def load_saved_seeds(self) -> None:
        saved = str(self.settings.value("chattts/saved_seeds", "42")).strip()
        seeds: list[str] = []
        for value in saved.split(","):
            value = value.strip()
            if value.isdigit() and value not in seeds:
                seeds.append(value)
        current = str(self.chattts_seed_spin.value())
        if current not in seeds:
            seeds.insert(0, current)
        self.chattts_seed_combo.blockSignals(True)
        self.chattts_seed_combo.clear()
        self.chattts_seed_combo.addItems(seeds)
        self.chattts_seed_combo.setCurrentText(current)
        self.chattts_seed_combo.blockSignals(False)

    def saved_seed_values(self) -> list[str]:
        values: list[str] = []
        for index in range(self.chattts_seed_combo.count()):
            value = self.chattts_seed_combo.itemText(index).strip()
            if value.isdigit() and value not in values:
                values.append(value)
        current = str(self.chattts_seed_spin.value())
        if current not in values:
            values.insert(0, current)
        return values

    def save_current_seed(self) -> None:
        seed = str(self.chattts_seed_spin.value())
        seeds = self.saved_seed_values()
        if seed in seeds:
            seeds.remove(seed)
        seeds.insert(0, seed)
        self.chattts_seed_combo.blockSignals(True)
        self.chattts_seed_combo.clear()
        self.chattts_seed_combo.addItems(seeds)
        self.chattts_seed_combo.setCurrentText(seed)
        self.chattts_seed_combo.blockSignals(False)
        self._save_settings()
        self.append_log(f"{t('seed_saved')}: {seed}")

    def on_seed_combo_changed(self, text: str) -> None:
        value = text.strip()
        if value.isdigit():
            self.chattts_seed_spin.setValue(int(value))

    def choose_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, t("choose_txt"), "", "Text files (*.txt);;All files (*.*)")
        if path:
            self.source_edit.setText(path)

    def choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, t("choose_output"), self.output_edit.text())
        if path:
            self.output_edit.setText(path)

    def open_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, t("choose_project"), self.output_edit.text())
        if path:
            self.project_path = Path(path)
            self.append_log(f"{t('opened_project')}: {self.project_path}")
            self.refresh_chapter_table()

    def update_rate_label(self, value: int) -> None:
        self.rate_label.setText(f"{value:+d}%")

    def prepare_project(self) -> None:
        source_text = self.source_edit.text().strip()
        output_text = self.output_edit.text().strip()
        if not source_text:
            QMessageBox.warning(self, t("missing_file_title"), t("missing_file_body"))
            return

        source = Path(source_text)
        if not source.exists() or not source.is_file():
            QMessageBox.warning(self, t("missing_file_title"), t("missing_file_body"))
            return

        output = Path(output_text or "output")
        if output.exists() and not output.is_dir():
            QMessageBox.warning(self, t("failed"), f"{t('output_folder')} 不是資料夾：{output}")
            return

        self._save_settings()
        worker = Worker(
            t("preparing"),
            prepare_project,
            progress_arg="progress_callback",
            source=source,
            output_root=output,
            voice=self.selected_voice(),
            locale=self.locale_combo.currentText().strip(),
            rate=self.rate_label.text(),
            max_segment_chars=self.segment_spin.value(),
        )
        worker.signals.finished.connect(self.on_prepare_finished)
        self.start_worker(worker)

    def load_voices(self) -> None:
        self._save_settings()
        worker = Worker(t("loading_voices"), self.fetch_voices, self.locale_combo.currentText())
        worker.signals.finished.connect(self.on_voices_finished)
        self.start_worker(worker)

    def fetch_voices(self, locale: str) -> list[dict]:
        return list_edge_voices_sync(locale)

    def run_synthesize(self) -> None:
        if self.project_path is None:
            QMessageBox.warning(self, t("missing_project_title"), t("missing_project_body"))
            return
        self._save_settings()
        if self.provider_combo.currentData() == "chattts":
            worker = Worker(
                t("synthesizing_chattts"),
                synthesize_project_chattts,
                progress_arg="progress_callback",
                project=load_project(self.project_path),
                chapter=None if self.chapter_spin.value() == 0 else self.chapter_spin.value(),
                force=self.force_check.isChecked(),
                prompt=self.chattts_prompt_edit.text().strip() or DEFAULT_CHAT_PROMPT,
                skip_refine_text=True,
                speaker_seed=None if self.chattts_seed_spin.value() == 0 else self.chattts_seed_spin.value(),
                source="huggingface",
                ffmpeg="ffmpeg",
            )
        elif self.provider_combo.currentData() == "fish":
            worker = Worker(
                "正在使用 Fish Speech API 轉檔",
                synthesize_project_fish,
                progress_arg="progress_callback",
                project=load_project(self.project_path),
                chapter=None if self.chapter_spin.value() == 0 else self.chapter_spin.value(),
                force=self.force_check.isChecked(),
                server_url=self.fish_url_edit.text().strip() or DEFAULT_FISH_SERVER_URL,
                api_key=self.fish_api_key_edit.text().strip(),
                reference_id=self.fish_reference_id_edit.text().strip(),
                seed=None if self.fish_seed_spin.value() == 0 else self.fish_seed_spin.value(),
                max_chunk_chars=self.fish_chunk_spin.value(),
                chunk_length=self.fish_api_chunk_spin.value(),
                max_new_tokens=self.fish_max_new_tokens_spin.value(),
                ffmpeg="ffmpeg",
            )
        else:
            worker = Worker(
                t("synthesizing"),
                synthesize_project_edge,
                progress_arg="progress_callback",
                project=load_project(self.project_path),
                voice=self.selected_voice(),
                rate=self.rate_label.text(),
                chapter=None if self.chapter_spin.value() == 0 else self.chapter_spin.value(),
                force=self.force_check.isChecked(),
                ffmpeg="ffmpeg",
            )
        worker.signals.finished.connect(self.on_synthesize_finished)
        self.start_worker(worker)

    def preview_chattts_voice(self) -> None:
        self._save_settings()
        output_root = Path(self.output_edit.text().strip() or "output")
        worker = Worker(
            t("previewing_chattts"),
            run_chattts_preview_isolated,
            text=self.chattts_preview_text_edit.text().strip() or DEFAULT_PREVIEW_TEXT,
            output_dir=output_root / "previews",
            prompt=self.chattts_prompt_edit.text().strip() or DEFAULT_CHAT_PROMPT,
            speaker_seed=None if self.chattts_seed_spin.value() == 0 else self.chattts_seed_spin.value(),
            source="huggingface",
            ffmpeg="ffmpeg",
        )
        worker.signals.finished.connect(self.on_preview_finished)
        self.start_worker(worker)

    def merge_full_book(self) -> None:
        if self.project_path is None:
            QMessageBox.warning(self, t("missing_project_title"), t("missing_project_body"))
            return
        worker = Worker(t("merging"), create_full_book_audio, self.project_path, ffmpeg="ffmpeg")
        worker.signals.finished.connect(lambda output: self.append_log(f"{t('full_output')}: {output}"))
        worker.signals.finished.connect(lambda _: self.refresh_chapter_table())
        self.start_worker(worker)

    def open_output_folder(self) -> None:
        if self.project_path is None:
            QMessageBox.warning(self, t("missing_project_title"), t("missing_project_body"))
            return
        subprocess.Popen(["explorer", str(self.project_path)])

    def start_worker(self, worker: Worker) -> None:
        self.active_workers.append(worker)
        self.set_busy(True)
        worker.signals.started.connect(self.append_log)
        worker.signals.progress.connect(self.on_progress)
        worker.signals.failed.connect(self.on_failed)
        worker.signals.completed.connect(lambda worker=worker: self.on_worker_completed(worker))
        self.thread_pool.start(worker)

    def on_worker_completed(self, worker: Worker) -> None:
        if worker in self.active_workers:
            self.active_workers.remove(worker)
        if not self.active_workers:
            self.set_busy(False)

    def on_prepare_finished(self, result) -> None:
        self.project_path = result.project.root
        self.append_log(summary_json(result.summary))
        self.refresh_chapter_table()

    def on_voices_finished(self, voices: list[dict]) -> None:
        self.voices = voices
        current = self.selected_voice()
        self.voice_combo.clear()
        for voice in voices:
            short_name = voice.get("ShortName")
            label = f"{short_name} - {voice.get('FriendlyName') or voice.get('DisplayName')}"
            self.voice_combo.addItem(label, short_name)
        if voices:
            self.voice_combo.setCurrentIndex(0)
        else:
            self.voice_combo.setEditText(current)
        self.append_log(t("loaded_voices", count=len(voices)))

    def on_synthesize_finished(self, results) -> None:
        for result in results:
            self.append_log(str(result))
        self.append_log(t("tts_done"))
        self.refresh_chapter_table()

    def on_preview_finished(self, output: Path) -> None:
        self.append_log(f"{t('preview_output')}: {output}")
        os.startfile(output)

    def refresh_chapter_table(self) -> None:
        if self.project_path is None:
            self.chapter_table.setRowCount(0)
            return
        try:
            manifest = load_project(self.project_path).load_manifest()
        except Exception as exc:
            self.append_log(f"{t('table_load_failed')}: {exc}")
            self.chapter_table.setRowCount(0)
            return

        chapters = manifest.get("chapters", [])
        self.chapter_table.setRowCount(len(chapters))
        for row, chapter in enumerate(chapters):
            values = [
                str(chapter.get("index", "")),
                str(chapter.get("title", "")),
                str(chapter.get("characters", "")),
                str(chapter.get("status", "")),
                str(chapter.get("output", "")),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in {0, 2}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.chapter_table.setItem(row, col, item)
        self.chapter_table.resizeColumnsToContents()
        self.chapter_table.horizontalHeader().setStretchLastSection(True)

    def on_table_selection_changed(self) -> None:
        items = self.chapter_table.selectedItems()
        if not items:
            return
        row = items[0].row()
        index_item = self.chapter_table.item(row, 0)
        if index_item is None:
            return
        try:
            self.chapter_spin.setValue(int(index_item.text()))
        except ValueError:
            pass

    def selected_voice(self) -> str:
        data = self.voice_combo.currentData()
        return str(data or self.voice_combo.currentText()).split(" - ", 1)[0].strip()

    def on_failed(self, error: str) -> None:
        self.set_busy(False)
        self.append_log(error)
        QMessageBox.critical(self, t("failed"), error.splitlines()[-1] if error else t("unknown_error"))

    def set_busy(self, busy: bool) -> None:
        for widget in [
            self.prepare_button,
            self.voices_button,
            self.synthesize_button,
            self.preview_voice_button,
            self.open_project_button,
            self.merge_full_button,
            self.refresh_button,
            self.open_folder_button,
        ]:
            widget.setEnabled(not busy)
        self.progress_label.setVisible(busy)
        self.progress.setVisible(busy)
        if busy:
            self.progress_started_at = time.monotonic()
            self.progress.setRange(0, 0)
            self.progress_label.setText("處理中...")
        else:
            self.progress_started_at = None
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self.progress_label.setText("待命")

    def on_progress(self, progress: object) -> None:
        if not isinstance(progress, dict):
            return
        current = int(progress.get("current") or 0)
        total = int(progress.get("total") or 0)
        message = str(progress.get("message") or "處理中...")
        if total > 0:
            current = max(0, min(current, total))
            self.progress.setRange(0, total)
            self.progress.setValue(current)
            percent = int((current / total) * 100)
            elapsed = 0.0 if self.progress_started_at is None else time.monotonic() - self.progress_started_at
            eta_text = ""
            if current > 0 and elapsed > 0:
                remaining = max(0.0, elapsed / current * (total - current))
                eta_text = f"｜已用 {self.format_duration(elapsed)}｜剩餘約 {self.format_duration(remaining)}"
            self.progress_label.setText(f"{message}｜{percent}%{eta_text}")
        else:
            self.progress.setRange(0, 0)
            self.progress_label.setText(message)

    @staticmethod
    def format_duration(seconds: float) -> str:
        total_seconds = max(0, int(seconds))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def append_log(self, text: str) -> None:
        self.log.appendPlainText(str(text))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--chattts-preview-worker":
        return run_chattts_preview_worker(Path(sys.argv[2]), Path(sys.argv[3]))
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
