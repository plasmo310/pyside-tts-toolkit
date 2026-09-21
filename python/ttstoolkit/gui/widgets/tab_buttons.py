"""どのタブの下端にも置く Run / Cancel のボタン行。

3 つのタブで同じものを使うので 1 つにまとめてある。押されたことを
シグナルで外へ伝えるだけで、実行するかどうかはタブと Controller が
決める。
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ttstoolkit.tool_config import ToolConfig


class TabButtonRow(QtWidgets.QWidget):
    """Run と Cancel を右寄せで並べた行。

    Attributes:
        __run_button (QtWidgets.QPushButton): 実行ボタン。
        __cancel_button (QtWidgets.QPushButton): 中断ボタン。
    """

    on_click_run_signal = QtCore.Signal()
    on_click_cancel_signal = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """行を組み立てる。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setProperty("class", "ButtonRow")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch()

        self.__cancel_button = QtWidgets.QPushButton("Cancel")
        self.__cancel_button.setProperty("class", "ButtonAction")
        self.__cancel_button.setFixedWidth(ToolConfig.CANCEL_BUTTON_WIDTH)
        self.__cancel_button.setEnabled(False)
        self.__cancel_button.setToolTip(
            "Stop before the next line starts; the current one finishes"
        )
        self.__cancel_button.clicked.connect(self.on_click_cancel_signal)
        layout.addWidget(self.__cancel_button)

        self.__run_button = QtWidgets.QPushButton("Run")
        self.__run_button.setProperty("class", "ButtonBlue")
        self.__run_button.setFixedWidth(ToolConfig.CANCEL_BUTTON_WIDTH)
        self.__run_button.setDefault(True)
        self.__run_button.clicked.connect(self.on_click_run_signal)
        layout.addWidget(self.__run_button)

    def set_running(self, is_running: bool) -> None:
        """実行中の見た目に切り替える。

        Args:
            is_running: 実行中なら True。
        """
        self.__run_button.setEnabled(not is_running)
        self.__cancel_button.setEnabled(is_running)
