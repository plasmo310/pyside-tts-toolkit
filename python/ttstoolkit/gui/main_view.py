"""メイン画面 View。

3 つのタブ (Synthesis / Voice Design / Script) とログ表示を並べるだけで、
合成もファイル書き出しもしない。Controller への通知は `on_*_signal`、
Controller からの反映は公開メソッドで行う。

見た目は `resources/ui/stylesheet.qss` に寄せ、ここでは
`setProperty("class", ...)` でタグを付けるだけにする。
"""

from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets

from ttstoolkit.gui.widgets.script_tab import ScriptTab
from ttstoolkit.gui.widgets.synthesis_tab import SynthesisTab
from ttstoolkit.gui.widgets.voice_design_tab import VoiceDesignTab
from ttstoolkit.tool_config import ToolConfig

# ログ欄に残す最大行数
_LOG_MAX_LINES = 20000

# 入力タブとログ欄の既定の高さ。
# 入力欄が多いので、タブ側は既定でスクロールせずに収まる高さにする。
_DEFAULT_SPLITTER_SIZES = [700, 160]

# Help メニューから開くドキュメント
_DOCUMENT_URL = "https://github.com/plasmo310/pyside-tts-toolkit"


class _LogPane(QtWidgets.QPlainTextEdit):
    """進捗とログを流す読み取り専用のテキスト欄。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """ログ欄を作る。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setProperty("class", "LogPane")
        self.setReadOnly(True)
        self.setMaximumBlockCount(_LOG_MAX_LINES)
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)

    def append_line(self, text: str) -> None:
        """1 行追記して末尾までスクロールする。

        Args:
            text: 追記する文字列。
        """
        self.appendPlainText(text)
        scroll_bar = self.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())


class MainView(QtWidgets.QMainWindow):
    """メイン画面 Viewクラス"""

    on_close_window_signal = QtCore.Signal()
    on_clear_settings_signal = QtCore.Signal()

    def __init__(self) -> None:
        """ウィンドウを組み立てる。"""
        super().__init__()
        self.setWindowTitle(ToolConfig.TOOL_TITLE)
        icon_path = ToolConfig.get_tool_icon_path()
        if icon_path:
            self.setWindowIcon(QtGui.QIcon(icon_path))
        self.resize(ToolConfig.WINDOW_WIDTH, ToolConfig.WINDOW_HEIGHT)
        self.__move_to_center()

        self.__build_menu_bar()
        self.__build_ui()

    def __move_to_center(self) -> None:
        """ウィンドウを画面の中央に置く。"""
        rect = self.frameGeometry()
        rect.moveCenter(
            QtWidgets.QApplication.primaryScreen().availableGeometry().center()
        )
        self.move(rect.topLeft())

    def __build_menu_bar(self) -> None:
        """メニューバーを組み立てる。"""
        file_menu = self.menuBar().addMenu("File")

        self.__clear_settings_action = file_menu.addAction(
            "Clear Saved Settings..."
        )
        self.__clear_settings_action.triggered.connect(
            self.on_clear_settings_signal
        )

        clear_log_action = file_menu.addAction("Clear Log")
        clear_log_action.triggered.connect(self.clear_log)

        file_menu.addSeparator()

        exit_action = file_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

        help_menu = self.menuBar().addMenu("Help")
        open_document_action = help_menu.addAction("Open Document")
        open_document_action.triggered.connect(self.open_document)

    def __build_ui(self) -> None:
        """中身を組み立てる。"""
        root_widget = QtWidgets.QWidget()
        root_widget.setProperty("class", "RootWidget")
        self.setCentralWidget(root_widget)

        main_layout = QtWidgets.QVBoxLayout(root_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.__build_content(), 1)

    def __build_content(self) -> QtWidgets.QWidget:
        """タブとログを縦に分割した領域を作る。"""
        content_area = QtWidgets.QWidget()
        content_area.setProperty("class", "ContentArea")

        outer_layout = QtWidgets.QVBoxLayout(content_area)
        outer_layout.setContentsMargins(16, 12, 16, 16)
        outer_layout.setSpacing(0)

        self.__splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.__splitter.setProperty("class", "MainSplitter")
        self.__splitter.setChildrenCollapsible(False)
        self.__splitter.setHandleWidth(12)
        self.__splitter.addWidget(self.__build_tabs())
        self.__splitter.addWidget(self.__build_log_panel())
        self.__splitter.setSizes(_DEFAULT_SPLITTER_SIZES)

        outer_layout.addWidget(self.__splitter)
        return content_area

    def __build_tabs(self) -> QtWidgets.QWidget:
        """3 つのタブを組み立てる。"""
        self.synthesis_tab = SynthesisTab()
        self.voice_design_tab = VoiceDesignTab()
        self.script_tab = ScriptTab()

        tab_widget = QtWidgets.QTabWidget()
        tab_widget.addTab(self.synthesis_tab, "Synthesis")
        tab_widget.addTab(self.voice_design_tab, "Voice Design")
        tab_widget.addTab(self.script_tab, "Script")
        return tab_widget

    def __build_log_panel(self) -> QtWidgets.QWidget:
        """ログのパネルを組み立てる。"""
        log_panel = QtWidgets.QFrame()
        log_panel.setProperty("class", "Panel")
        # 低くしてタブ側に高さを譲る。ドラッグで広げられる。
        log_panel.setMinimumHeight(150)

        layout = QtWidgets.QVBoxLayout(log_panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header_label = QtWidgets.QLabel("Log")
        header_label.setProperty("class", "PanelHeader")
        layout.addWidget(header_label)

        self.__log_pane = _LogPane()
        layout.addWidget(self.__log_pane, 1)
        return log_panel

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """ウィンドウを閉じるときに Controller へ通知する。"""
        self.on_close_window_signal.emit()
        super().closeEvent(event)

    def append_log(self, text: str) -> None:
        """ログを 1 行追記する。

        Args:
            text: 追記する文字列。
        """
        self.__log_pane.append_line(text)

    def clear_log(self) -> None:
        """ログを消す。"""
        self.__log_pane.clear()

    def open_document(self) -> None:
        """プロジェクトのドキュメントを既定ブラウザで開く。"""
        if not QtGui.QDesktopServices.openUrl(QtCore.QUrl(_DOCUMENT_URL)):
            self.append_log(
                f"[warn] Could not open the documentation: {_DOCUMENT_URL}"
            )

    def set_running(self, is_running: bool) -> None:
        """実行中の見た目に切り替える。

        Args:
            is_running: 実行中なら True。
        """
        self.synthesis_tab.set_running(is_running)
        self.voice_design_tab.set_running(is_running)
        self.script_tab.set_running(is_running)
        self.__clear_settings_action.setEnabled(not is_running)

    def reset_settings(self) -> None:
        """ウィンドウと各タブをコード上の既定値へ戻す。"""
        self.synthesis_tab.set_state({})
        self.voice_design_tab.set_state({})
        self.script_tab.set_state({})
        self.__splitter.setSizes(_DEFAULT_SPLITTER_SIZES)
        self.showNormal()
        self.resize(ToolConfig.WINDOW_WIDTH, ToolConfig.WINDOW_HEIGHT)
        self.__move_to_center()

    def show_confirm_dialog(self, title: str, message: str) -> bool:
        """確認ダイアログを表示する。

        Args:
            title: ダイアログのタイトル。
            message: ダイアログのメッセージ。

        Returns:
            bool: Yes が選択された場合は True、それ以外は False。
        """
        result = QtWidgets.QMessageBox.warning(
            self,
            title,
            message,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.Yes,
        )
        return result == QtWidgets.QMessageBox.StandardButton.Yes

    def show_error_dialog(self, message: str) -> None:
        """エラーダイアログを表示する。

        Args:
            message: 表示する文言。
        """
        QtWidgets.QMessageBox.critical(self, ToolConfig.TOOL_TITLE, message)

    def open_output_folder(self, path: str) -> bool:
        """出力フォルダをファイルマネージャーで開く。

        Args:
            path: 出力ディレクトリのパス。

        Returns:
            bool: ファイルマネージャーを起動できた場合は True。
        """
        directory = os.path.abspath(path)
        if not os.path.isdir(directory):
            return False
        return QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(directory)
        )

    def get_window_state(self) -> dict[str, QtCore.QByteArray]:
        """現在のウィンドウ状態を返す。

        Returns:
            dict[str, QtCore.QByteArray]: 位置/サイズと分割位置。
        """
        return {
            "geometry": self.saveGeometry(),
            "splitter": self.__splitter.saveState(),
        }

    def restore_window_state(
        self, window_state: dict[str, QtCore.QByteArray]
    ) -> None:
        """保存済みのウィンドウ状態を復元する。

        Args:
            window_state: `get_window_state()` が返した辞書。
        """
        geometry = window_state.get("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitter = window_state.get("splitter")
        if splitter:
            self.__splitter.restoreState(splitter)
