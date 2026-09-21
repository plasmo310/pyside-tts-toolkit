"""キャラクター台本からまとめて音声を作るタブ。

`ttstoolkit.cli.script` と同じことを画面から指定できるようにする。
台本の書き方は `ttstoolkit.engine.script` の docstring を参照。

Run を押すと入力内容を `ScriptTabRequest` に詰めて emit するだけで、
合成そのものは Controller / Model の担当。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6 import QtCore, QtWidgets

from ttstoolkit.engine.paths import OUTPUT_DIR, SCRIPT_DIR
from ttstoolkit.gui.widgets.option_rows import (
    DirPathRow,
    FilePathRow,
    build_form_scroll_area,
    build_group,
    build_labeled_row,
)
from ttstoolkit.gui.widgets.tab_buttons import TabButtonRow
from ttstoolkit.tool_config import ToolConfig

# 台詞と台詞のあいだの既定の間 (秒)
_DEFAULT_GAP_SEC = 0.3


@dataclass
class ScriptTabRequest:
    """台本合成の実行内容。

    Attributes:
        cast_path: キャスト定義 TOML のパス。
        script_path: 台本テキストのパス。
        output_dir: 書き出し先ディレクトリ。
        gap_sec: manifest の start_sec を出すときの台詞間の間 (秒)。
        keep_going: 1 台詞失敗しても残りを続けるか。
    """

    cast_path: str
    script_path: str
    output_dir: str
    gap_sec: float = _DEFAULT_GAP_SEC
    keep_going: bool = False


class ScriptTab(QtWidgets.QWidget):
    """台本合成タブ"""

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
        layout.addWidget(self.__build_input_group())
        layout.addWidget(self.__build_option_group())
        layout.addStretch()

        return build_form_scroll_area(content)

    def __build_hint(self) -> QtWidgets.QWidget:
        """このタブの使い方を 1 行で説明するラベルを作る。"""
        hint = QtWidgets.QLabel(
            "The cast file assigns a voice to each character; the script "
            "is plain text written as '<character>: <line>'. Each line "
            "becomes one wav, and manifest.json keeps their order."
        )
        hint.setProperty("class", "HintLabel")
        hint.setWordWrap(True)
        return hint

    def __build_input_group(self) -> QtWidgets.QWidget:
        """入力と書き出し先のグループを作る。"""
        self.__cast_row = FilePathRow(
            "Cast File", SCRIPT_DIR, ToolConfig.CAST_FILE_FILTER
        )
        self.__script_row = FilePathRow(
            "Script File", SCRIPT_DIR, ToolConfig.SCRIPT_FILE_FILTER
        )
        self.__output_dir_row = DirPathRow("Output Dir", OUTPUT_DIR)
        self.__output_dir_row.set_path(OUTPUT_DIR)

        return build_group(
            "Input / Output",
            self.__cast_row,
            self.__script_row,
            self.__output_dir_row,
        )

    def __build_option_group(self) -> QtWidgets.QWidget:
        """実行の細かい指定のグループを作る。"""
        self.__gap_spin = QtWidgets.QDoubleSpinBox()
        self.__gap_spin.setRange(0.0, 5.0)
        self.__gap_spin.setSingleStep(0.1)
        self.__gap_spin.setValue(_DEFAULT_GAP_SEC)
        self.__gap_spin.setFixedWidth(120)
        self.__gap_spin.setToolTip(
            "Written into manifest.json as start_sec; no silence is added "
            "to the wav files themselves"
        )

        self.__keep_going_check = QtWidgets.QCheckBox(
            "continue after a failed line"
        )

        return build_group(
            "Options",
            build_labeled_row("Gap", self.__gap_spin, stretch_last=False),
            build_labeled_row(
                "On Failure",
                self.__keep_going_check,
                stretch_last=False,
            ),
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

    def request(self) -> ScriptTabRequest:
        """入力内容から実行内容を組み立てる。

        Returns:
            ScriptTabRequest: 画面で指定された実行内容。
        """
        return ScriptTabRequest(
            cast_path=self.__cast_row.path(),
            script_path=self.__script_row.path(),
            output_dir=self.__output_dir_row.path(),
            gap_sec=self.__gap_spin.value(),
            keep_going=self.__keep_going_check.isChecked(),
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
            "cast_path": request.cast_path,
            "script_path": request.script_path,
            "output_dir": request.output_dir,
            "gap_sec": request.gap_sec,
            "keep_going": request.keep_going,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """保存済みの入力値を画面に戻す。

        Args:
            state: `state()` が返した辞書。
        """
        self.__cast_row.set_path(state.get("cast_path", ""))
        self.__script_row.set_path(state.get("script_path", ""))
        self.__output_dir_row.set_path(state.get("output_dir", OUTPUT_DIR))
        self.__gap_spin.setValue(float(state.get("gap_sec", _DEFAULT_GAP_SEC)))
        self.__keep_going_check.setChecked(
            bool(state.get("keep_going", False))
        )
