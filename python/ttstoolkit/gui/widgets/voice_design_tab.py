"""オリジナルの声を作るタブ。

参照音声を持っていなくても、声を文章で説明すればモデルがその声を
作ってくれる (Voice Design)。ただし作った声は毎回わずかに揺れるので、
**気に入った 1 本を `input/voices/` に残して以後はそれをクローンの
参照音声として使う** のが安定した運用になる。このタブは既定の書き出し
先を `input/voices/` にしてあり、その流れをそのままなぞれる。

Run を押すと入力内容を `VoiceDesignTabRequest` に詰めて emit するだけで、
生成そのものは Controller / Model の担当。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6 import QtCore, QtWidgets

from ttstoolkit.definitions import EngineType
from ttstoolkit.engine.paths import VOICES_DIR
from ttstoolkit.engine.types import Capability
from ttstoolkit.gui.widgets.option_rows import (
    DirPathRow,
    EngineOptionsGroup,
    TextAreaRow,
    build_form_scroll_area,
    build_group,
    build_labeled_row,
    build_seed_spin,
)
from ttstoolkit.gui.widgets.tab_buttons import TabButtonRow

_DESIGN_PLACEHOLDER = (
    "20 代女性のはきはきした明るい声。少し早口で、語尾が弾む。"
)

_SAMPLE_PLACEHOLDER = "こんにちは。この声でナレーションを読み上げます。"

# 書き出しファイル名の既定値
_DEFAULT_OUTPUT_NAME = "master.wav"


@dataclass
class VoiceDesignTabRequest:
    """オリジナルボイス作成の実行内容。

    Attributes:
        engine: 使うエンジン名。
        voice_design: 声を説明する文章。
        text: 試し読みさせるテキスト。
        output_dir: 書き出し先ディレクトリ。
        output_name: 書き出すファイル名。
        language: 言語コード。
        seed: 乱数シード。
    """

    engine: str
    voice_design: str
    text: str
    output_dir: str
    output_name: str
    language: str | None = None
    seed: int | None = None


class VoiceDesignTab(QtWidgets.QWidget):
    """オリジナルボイス作成タブ"""

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

    def __build_form(self) -> QtWidgets.QWidget:
        """入力欄をまとめたスクロール領域を作る。"""
        content = QtWidgets.QWidget()
        content.setProperty("class", "FormArea")
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        layout.addWidget(self.__build_hint())
        # 声を設計できるエンジンだけを並べる
        self.__engine_options = EngineOptionsGroup(Capability.VOICE_DESIGN)
        layout.addWidget(self.__engine_options)
        layout.addWidget(self.__build_design_group())
        layout.addWidget(self.__build_output_group())
        layout.addStretch()

        return build_form_scroll_area(content)

    def __build_hint(self) -> QtWidgets.QWidget:
        """このタブの使い方を 1 行で説明するラベルを作る。"""
        hint = QtWidgets.QLabel(
            "Describe a voice, listen to the result, and keep the take you "
            "like in input/voices. Clone from that file afterwards so the "
            "voice stays the same."
        )
        hint.setProperty("class", "HintLabel")
        hint.setWordWrap(True)
        return hint

    def __build_design_group(self) -> QtWidgets.QWidget:
        """声の設計のグループを作る。"""
        self.__design_row = TextAreaRow("Voice Design", _DESIGN_PLACEHOLDER)
        self.__text_row = TextAreaRow("Sample Text", _SAMPLE_PLACEHOLDER)
        self.__seed_spin = build_seed_spin()
        return build_group(
            "Design",
            self.__design_row,
            self.__text_row,
            build_labeled_row("Seed", self.__seed_spin, stretch_last=False),
        )

    def __build_output_group(self) -> QtWidgets.QWidget:
        """書き出し先のグループを作る。"""
        self.__output_dir_row = DirPathRow("Output Dir", VOICES_DIR)
        self.__output_dir_row.set_path(VOICES_DIR)

        self.__output_name_edit = QtWidgets.QLineEdit()
        self.__output_name_edit.setText(_DEFAULT_OUTPUT_NAME)

        return build_group(
            "Output",
            self.__output_dir_row,
            build_labeled_row("Output File", self.__output_name_edit),
        )

    def __build_buttons(self) -> QtWidgets.QWidget:
        """Run / Cancel ボタンの行を作る。"""
        self.__buttons = TabButtonRow()
        self.__buttons.on_click_run_signal.connect(self.__on_click_run_button)
        self.__buttons.on_click_cancel_signal.connect(
            self.on_click_cancel_signal
        )
        return self.__buttons

    def __on_click_run_button(self) -> None:
        """Run ボタン押下時処理"""
        self.on_click_run_signal.emit(self.request())

    def request(self) -> VoiceDesignTabRequest:
        """入力内容から実行内容を組み立てる。

        Returns:
            VoiceDesignTabRequest: 画面で指定された実行内容。
        """
        seed = self.__seed_spin.value()
        return VoiceDesignTabRequest(
            engine=self.__engine_options.engine(),
            voice_design=self.__design_row.text(),
            text=self.__text_row.text(),
            output_dir=self.__output_dir_row.path(),
            output_name=self.__output_name_edit.text().strip(),
            language=self.__engine_options.language(),
            seed=None if seed < 0 else seed,
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
            "engine": request.engine,
            "language": request.language,
            "voice_design": request.voice_design,
            "text": request.text,
            "output_dir": request.output_dir,
            "output_name": request.output_name,
            "seed": self.__seed_spin.value(),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """保存済みの入力値を画面に戻す。

        Args:
            state: `state()` が返した辞書。
        """
        self.__engine_options.set_state(
            state.get("engine", EngineType.IRODORI.value),
            state.get("language"),
        )
        self.__design_row.set_text(state.get("voice_design", ""))
        self.__text_row.set_text(state.get("text", ""))
        self.__output_dir_row.set_path(state.get("output_dir", VOICES_DIR))
        self.__output_name_edit.setText(
            state.get("output_name", _DEFAULT_OUTPUT_NAME)
        )
        self.__seed_spin.setValue(int(state.get("seed", -1)))
