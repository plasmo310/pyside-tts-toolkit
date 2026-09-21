"""テキストから音声を作るタブ。

`ttstoolkit.cli` の synth と同じことを画面から指定できるようにする。
Run を押すと入力内容を `SynthesisTabRequest` に詰めて emit するだけで、
合成そのものは Controller / Model の担当。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6 import QtCore, QtWidgets

from ttstoolkit.core.engine import EngineType
from ttstoolkit.core.paths import OUTPUT_DIR, VOICES_DIR
from ttstoolkit.definitions import VoiceSourceType
from ttstoolkit.gui.widgets.option_rows import (
    DirPathRow,
    EngineOptionsGroup,
    FilePathRow,
    NoWheelComboBox,
    TextAreaRow,
    build_form_scroll_area,
    build_group,
    build_labeled_row,
    build_seed_spin,
    build_speed_spin,
    select_combo_data,
)
from ttstoolkit.gui.widgets.tab_buttons import TabButtonRow
from ttstoolkit.tool_config import ToolConfig

_TEXT_PLACEHOLDER = "こんにちは。音声合成のテストです。"

_DESIGN_PLACEHOLDER = "落ち着いた低めの女性の声。ゆっくりで、丁寧な話し方。"


@dataclass
class SynthesisTabRequest:
    """テキスト合成の実行内容。

    Attributes:
        engine: 使うエンジン名。
        text: 読み上げるテキスト。
        output_dir: 書き出し先ディレクトリ。
        output_name: 書き出すファイル名。空ならテキストから決める。
        language: 言語コード。
        reference_audio: 参照音声のパス。
        reference_text: 参照音声の書き起こし。
        voice_design: 文章による声の指定。
        seed: 乱数シード。
        speed: 話速。
    """

    engine: str
    text: str
    output_dir: str
    output_name: str = ""
    language: str | None = None
    reference_audio: str | None = None
    reference_text: str | None = None
    voice_design: str | None = None
    seed: int | None = None
    speed: float = 1.0


class SynthesisTab(QtWidgets.QWidget):
    """テキスト合成タブ"""

    on_click_run_signal = QtCore.Signal(object)
    on_click_cancel_signal = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """タブを組み立てる。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.__build_form(), 1)
        layout.addWidget(self.__build_buttons())
        self.__on_change_voice_source(0)

    def __build_form(self) -> QtWidgets.QWidget:
        """入力欄をまとめたスクロール領域を作る。"""
        content = QtWidgets.QWidget()
        content.setProperty("class", "FormArea")
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        layout.addWidget(self.__build_input_group())
        self.__engine_options = EngineOptionsGroup()
        layout.addWidget(self.__engine_options)
        layout.addWidget(self.__build_voice_group())
        layout.addStretch()

        return build_form_scroll_area(content)

    def __build_input_group(self) -> QtWidgets.QWidget:
        """入力と書き出し先のグループを作る。"""
        self.__text_row = TextAreaRow("Text", _TEXT_PLACEHOLDER)

        self.__output_dir_row = DirPathRow("Output Dir", OUTPUT_DIR)
        self.__output_dir_row.set_path(OUTPUT_DIR)

        self.__output_name_edit = QtWidgets.QLineEdit()
        self.__output_name_edit.setPlaceholderText(
            "derived from the text when empty"
        )

        return build_group(
            "Input / Output",
            self.__text_row,
            self.__output_dir_row,
            build_labeled_row("Output File", self.__output_name_edit),
        )

    def __build_voice_group(self) -> QtWidgets.QWidget:
        """声の決め方のグループを作る。"""
        self.__source_combo = NoWheelComboBox()
        for source_type in VoiceSourceType:
            self.__source_combo.addItem(source_type.label, source_type)
        self.__source_combo.currentIndexChanged.connect(
            self.__on_change_voice_source
        )

        self.__reference_row = FilePathRow(
            "Reference Audio", VOICES_DIR, ToolConfig.AUDIO_FILE_FILTER
        )
        self.__reference_text_edit = QtWidgets.QLineEdit()
        self.__reference_text_edit.setPlaceholderText(
            "what the reference audio says (improves Qwen cloning)"
        )
        self.__reference_text_row = build_labeled_row(
            "Reference Text", self.__reference_text_edit
        )

        self.__design_row = TextAreaRow("Voice Design", _DESIGN_PLACEHOLDER)

        self.__seed_spin = build_seed_spin()
        self.__speed_spin = build_speed_spin()

        return build_group(
            "Voice",
            build_labeled_row("Voice Source", self.__source_combo),
            self.__reference_row,
            self.__reference_text_row,
            self.__design_row,
            build_labeled_row("Seed", self.__seed_spin, stretch_last=False),
            build_labeled_row("Speed", self.__speed_spin, stretch_last=False),
        )

    def __build_buttons(self) -> QtWidgets.QWidget:
        """Run / Cancel ボタンの行を作る。"""
        self.__buttons = TabButtonRow()
        self.__buttons.on_click_run_signal.connect(self.__on_click_run_button)
        self.__buttons.on_click_cancel_signal.connect(
            self.on_click_cancel_signal
        )
        return self.__buttons

    def __on_change_voice_source(self, index: int) -> None:
        """声の決め方に応じて、関係のない入力欄を隠す。

        3 つの決め方は排他なので、無効化ではなく消す。そのぶん
        フォームが短くなり、いま何を入れればよいかも迷わない。

        Args:
            index: 選ばれた項目の位置。
        """
        source = self.__source_combo.currentData()
        is_reference = source is VoiceSourceType.REFERENCE
        is_design = source is VoiceSourceType.DESIGN
        self.__reference_row.setVisible(is_reference)
        self.__reference_text_row.setVisible(is_reference)
        self.__design_row.setVisible(is_design)

    def __on_click_run_button(self) -> None:
        """Run ボタン押下時処理"""
        self.on_click_run_signal.emit(self.request())

    def request(self) -> SynthesisTabRequest:
        """入力内容から実行内容を組み立てる。

        Returns:
            SynthesisTabRequest: 画面で指定された実行内容。
        """
        source = self.__source_combo.currentData()
        is_reference = source is VoiceSourceType.REFERENCE
        is_design = source is VoiceSourceType.DESIGN
        seed = self.__seed_spin.value()
        return SynthesisTabRequest(
            engine=self.__engine_options.engine(),
            text=self.__text_row.text(),
            output_dir=self.__output_dir_row.path(),
            output_name=self.__output_name_edit.text().strip(),
            language=self.__engine_options.language(),
            reference_audio=(
                self.__reference_row.path() or None if is_reference else None
            ),
            reference_text=(
                self.__reference_text_edit.text().strip() or None
                if is_reference
                else None
            ),
            voice_design=(
                self.__design_row.text() or None if is_design else None
            ),
            seed=None if seed < 0 else seed,
            speed=self.__speed_spin.value(),
        )

    def set_running(self, is_running: bool) -> None:
        """実行中の見た目に切り替える。

        Args:
            is_running: 実行中なら True。
        """
        self.__buttons.set_running(is_running)

    def state(self) -> dict[str, Any]:
        """保存する入力値を返す。"""
        request = self.request()
        return {
            "engine": self.__engine_options.engine(),
            "language": self.__engine_options.language(),
            "text": request.text,
            "output_dir": request.output_dir,
            "output_name": request.output_name,
            "voice_source": self.__source_combo.currentData().key,
            "reference_audio": self.__reference_row.path(),
            "reference_text": self.__reference_text_edit.text(),
            "voice_design": self.__design_row.text(),
            "seed": self.__seed_spin.value(),
            "speed": self.__speed_spin.value(),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """保存済みの入力値を画面に戻す。

        Args:
            state: `state()` が返した辞書。
        """
        self.__engine_options.set_state(
            state.get("engine", EngineType.QWEN.value),
            state.get("language"),
        )
        self.__text_row.set_text(state.get("text", ""))
        self.__output_dir_row.set_path(state.get("output_dir", OUTPUT_DIR))
        self.__output_name_edit.setText(state.get("output_name", ""))
        select_combo_data(
            self.__source_combo,
            VoiceSourceType.from_key(state.get("voice_source")),
        )
        self.__reference_row.set_path(state.get("reference_audio", ""))
        self.__reference_text_edit.setText(state.get("reference_text", ""))
        self.__design_row.set_text(state.get("voice_design", ""))
        self.__seed_spin.setValue(int(state.get("seed", -1)))
        self.__speed_spin.setValue(float(state.get("speed", 1.0)))
        self.__on_change_voice_source(0)
