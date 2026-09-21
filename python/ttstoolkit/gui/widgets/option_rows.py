"""タブで使い回す入力行のウィジェット。

どの行も「左にラベル、右に入力欄」で幅を揃える。値の取り出しは
`path()` / `text()` のような素の Python 型を返すメソッドで行い、
Qt のウィジェットをタブの外へ露出させない。

縦位置は行の高さを `ToolConfig.ROW_HEIGHT` に固定し、中に置く
ウィジェットを全部 `AlignVCenter` で入れることで揃える。
"""

from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets

from ttstoolkit.definitions import LanguageType
from ttstoolkit.engine.registry import available_engines
from ttstoolkit.engine.types import Capability
from ttstoolkit.tool_config import ToolConfig

# 行の中身を縦中央に揃えるための指定
_ALIGN_V_CENTER = QtCore.Qt.AlignmentFlag.AlignVCenter

# Browse ボタンの幅
_BROWSE_BUTTON_WIDTH = 34


def build_label(label_text: str) -> QtWidgets.QLabel:
    """入力行の左に置く、幅を揃えたラベルを作る。

    Args:
        label_text: 表示する文字列。

    Returns:
        QtWidgets.QLabel: 幅を固定し、縦中央に寄せたラベル。
    """
    label = QtWidgets.QLabel(label_text)
    label.setProperty("class", "RowLabel")
    label.setFixedWidth(ToolConfig.LABEL_WIDTH)
    label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | _ALIGN_V_CENTER)
    return label


def build_row_widget() -> tuple[QtWidgets.QWidget, QtWidgets.QHBoxLayout]:
    """高さを揃えた空の 1 行と、そのレイアウトを作る。

    Returns:
        tuple[QtWidgets.QWidget, QtWidgets.QHBoxLayout]: 行とレイアウト。
    """
    row = QtWidgets.QWidget()
    row.setProperty("class", "OptionRow")
    row.setFixedHeight(ToolConfig.ROW_HEIGHT)

    layout = QtWidgets.QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.setAlignment(_ALIGN_V_CENTER)
    return row, layout


def build_labeled_row(
    label_text: str,
    *widgets: QtWidgets.QWidget,
    stretch_last: bool = True,
) -> QtWidgets.QWidget:
    """ラベルと任意個のウィジェットを 1 行に並べる。

    Args:
        label_text: 左に置くラベルの文字列。
        *widgets: 右に並べるウィジェット。
        stretch_last: 最後のウィジェットを横に伸ばすか。入力欄なら
            True、スピンボックスのように幅を固定したいものは False。

    Returns:
        QtWidgets.QWidget: 1 行ぶんのウィジェット。
    """
    row, layout = build_row_widget()
    layout.addWidget(build_label(label_text), 0, _ALIGN_V_CENTER)
    for index, widget in enumerate(widgets):
        is_last = index == len(widgets) - 1
        stretch = 1 if (is_last and stretch_last) else 0
        layout.addWidget(widget, stretch, _ALIGN_V_CENTER)
    if not stretch_last:
        layout.addStretch()
    return row


def build_group(title: str, *rows: QtWidgets.QWidget) -> QtWidgets.QGroupBox:
    """入力行をまとめたグループを作る。

    余白は QSS 側 (`QGroupBox` の padding) に任せるので、ここでは
    レイアウトの margin を 0 にする。全部の行を同じグループの中に
    置くことで、ラベルの左端がタブ内で揃う。

    Args:
        title: グループの見出し。
        *rows: 縦に並べる行。

    Returns:
        QtWidgets.QGroupBox: 行を並べたグループ。
    """
    group = QtWidgets.QGroupBox(title)
    layout = QtWidgets.QVBoxLayout(group)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    for row in rows:
        layout.addWidget(row)
    return group


def build_form_scroll_area(
    content: QtWidgets.QWidget,
) -> QtWidgets.QScrollArea:
    """フォームを載せるスクロール領域を作る。

    縦スクロールバーの場所は常に空けておく。出たり消えたりすると
    タブごとに入力欄の幅がずれてしまうため。スクロールが不要なときは
    スクロールバーを無効にして、QSS 側でつまみを消す。

    Args:
        content: 載せるウィジェット。

    Returns:
        QtWidgets.QScrollArea: 設定済みのスクロール領域。
    """
    scroll_area = QtWidgets.QScrollArea()
    scroll_area.setProperty("class", "FormScroll")
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scroll_area.setHorizontalScrollBarPolicy(
        QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    scroll_area.setVerticalScrollBarPolicy(
        QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    )
    scroll_area.setWidget(content)

    scroll_bar = scroll_area.verticalScrollBar()

    def update_scroll_bar_enabled(minimum: int, maximum: int) -> None:
        scroll_bar.setEnabled(maximum > minimum)

    scroll_bar.rangeChanged.connect(update_scroll_bar_enabled)
    update_scroll_bar_enabled(scroll_bar.minimum(), scroll_bar.maximum())
    return scroll_area


def select_combo_data(combo: QtWidgets.QComboBox, data: object) -> None:
    """`addItem(表示名, データ)` で入れた項目を、データで選び直す。

    Args:
        combo: 対象のコンボボックス。
        data: 選びたい項目のデータ。見つからなければ何もしない。
    """
    index = combo.findData(data)
    if index >= 0:
        combo.setCurrentIndex(index)


class NoWheelComboBox(QtWidgets.QComboBox):
    """閉じた状態でホイール操作による選択変更をしないコンボボックス。"""

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """ホイールイベントを親へ渡し、フォームのスクロールに使う。"""
        event.ignore()


class _PathRowBase(QtWidgets.QWidget):
    """パス入力行の共通部分 (ラベル + 入力欄 + Browse ボタン)。

    Attributes:
        _default_dir (str): ダイアログを開く既定の場所。
    """

    def __init__(
        self,
        label_text: str,
        default_dir: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """行を組み立てる。

        Args:
            label_text: 左に置くラベルの文字列。
            default_dir: 入力欄が空のときにダイアログを開く場所。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._default_dir = default_dir
        self.setProperty("class", "OptionRow")
        self.setFixedHeight(ToolConfig.ROW_HEIGHT)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(_ALIGN_V_CENTER)
        layout.addWidget(build_label(label_text), 0, _ALIGN_V_CENTER)

        self.__path_edit = QtWidgets.QLineEdit()
        layout.addWidget(self.__path_edit, 1, _ALIGN_V_CENTER)

        browse_button = QtWidgets.QPushButton("...")
        browse_button.setProperty("class", "EllipsisButton")
        browse_button.setFixedWidth(_BROWSE_BUTTON_WIDTH)
        browse_button.clicked.connect(self._on_click_browse_button)
        layout.addWidget(browse_button, 0, _ALIGN_V_CENTER)

    def _on_click_browse_button(self) -> None:
        """Browse ボタン押下時処理。サブクラスで実装する。"""
        raise NotImplementedError

    def _start_dir(self) -> str:
        """ダイアログを開く場所を決める。

        入力済みならそのパスの場所、空なら既定の置き場。
        """
        current = self.path()
        if current:
            return os.path.dirname(os.path.abspath(current))
        return self._default_dir

    def path(self) -> str:
        """入力されているパスを返す (前後の空白は落とす)。"""
        return self.__path_edit.text().strip()

    def set_path(self, path: str) -> None:
        """パスを設定する。

        Args:
            path: 設定するパス。
        """
        self.__path_edit.setText(path)


class FilePathRow(_PathRowBase):
    """ファイルパスの入力行。

    Attributes:
        __file_filter (str): ダイアログのファイルフィルタ。
    """

    def __init__(
        self,
        label_text: str,
        default_dir: str,
        file_filter: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """行を組み立てる。

        Args:
            label_text: 左に置くラベルの文字列。
            default_dir: 入力欄が空のときにダイアログを開く場所。
            file_filter: ダイアログのファイルフィルタ。
            parent: 親ウィジェット。
        """
        super().__init__(label_text, default_dir, parent)
        self.__file_filter = file_filter

    def _on_click_browse_button(self) -> None:
        """Browse ボタン押下時処理"""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select File", self._start_dir(), self.__file_filter
        )
        if path:
            self.set_path(os.path.normpath(path))


class DirPathRow(_PathRowBase):
    """ディレクトリパスの入力行。"""

    def _on_click_browse_button(self) -> None:
        """Browse ボタン押下時処理"""
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Directory", self._start_dir()
        )
        if path:
            self.set_path(os.path.normpath(path))

    def _start_dir(self) -> str:
        """ダイアログを開く場所を決める。

        ディレクトリなので、入力済みならその場所自体を開く。
        """
        current = self.path()
        return current if current else self._default_dir


class TextAreaRow(QtWidgets.QWidget):
    """複数行テキストの入力行。

    台詞や声の指示は 1 行に収まらないので、ラベルを上端に寄せて
    右側に高さのある入力欄を置く。

    Attributes:
        __text_edit (QtWidgets.QPlainTextEdit): 入力欄。
    """

    def __init__(
        self,
        label_text: str,
        placeholder: str = "",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """行を組み立てる。

        Args:
            label_text: 左に置くラベルの文字列。
            placeholder: 空のときに薄く出す文字列。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setProperty("class", "OptionRow")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = build_label(label_text)
        label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignTop
        )
        layout.addWidget(label, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        self.__text_edit = QtWidgets.QPlainTextEdit()
        self.__text_edit.setProperty("class", "TextArea")
        self.__text_edit.setFixedHeight(ToolConfig.TEXT_EDIT_HEIGHT)
        self.__text_edit.setPlaceholderText(placeholder)
        layout.addWidget(self.__text_edit, 1)

    def text(self) -> str:
        """入力されている文字列を返す (前後の空白は落とす)。"""
        return self.__text_edit.toPlainText().strip()

    def set_text(self, text: str) -> None:
        """文字列を設定する。

        Args:
            text: 設定する文字列。
        """
        self.__text_edit.setPlainText(text)


def build_seed_spin() -> QtWidgets.QSpinBox:
    """乱数シードのスピンボックスを作る。

    -1 を「指定しない」の意味に使う。

    Returns:
        QtWidgets.QSpinBox: 設定済みのスピンボックス。
    """
    spin = QtWidgets.QSpinBox()
    spin.setRange(-1, 2147483647)
    spin.setValue(-1)
    spin.setSpecialValueText("random")
    spin.setFixedWidth(120)
    spin.setToolTip("Fix the seed to reproduce the same audio; -1 is random")
    return spin


def build_speed_spin() -> QtWidgets.QDoubleSpinBox:
    """話速のスピンボックスを作る。

    Returns:
        QtWidgets.QDoubleSpinBox: 設定済みのスピンボックス。
    """
    spin = QtWidgets.QDoubleSpinBox()
    spin.setRange(0.5, 2.0)
    spin.setSingleStep(0.05)
    spin.setValue(1.0)
    spin.setFixedWidth(120)
    spin.setToolTip("Only Irodori supports this; others must stay at 1.00")
    return spin


class EngineOptionsGroup(QtWidgets.QGroupBox):
    """どのエンジンでどの言語を喋らせるかを選ぶグループ。

    対応していないパラメータを渡すとエンジンはエラーを返すので、
    タブによっては必要な機能を持つエンジンだけを並べる。

    Attributes:
        __engine_combo (NoWheelComboBox): エンジンの選択。
        __language_combo (NoWheelComboBox): 言語の選択。
    """

    on_change_engine_signal = QtCore.Signal(str)

    def __init__(
        self,
        required_capability: Capability | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """グループを組み立てる。

        Args:
            required_capability: 並べるエンジンに必要な機能。None なら
                すべてのエンジンを並べる。
            parent: 親ウィジェット。
        """
        super().__init__("Engine", parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.__engine_combo = NoWheelComboBox()
        for name, spec in available_engines().items():
            if required_capability and not spec.supports(required_capability):
                continue
            self.__engine_combo.addItem(name, name)
            index = self.__engine_combo.count() - 1
            self.__engine_combo.setItemData(
                index,
                spec.description,
                QtCore.Qt.ItemDataRole.ToolTipRole,
            )
        self.__engine_combo.currentIndexChanged.connect(
            self.__on_change_engine
        )
        layout.addWidget(build_labeled_row("Engine", self.__engine_combo))

        self.__language_combo = NoWheelComboBox()
        for language_type in LanguageType:
            self.__language_combo.addItem(language_type.label, language_type)
        self.__language_combo.setToolTip(
            "Irodori is Japanese only; Auto leaves it to the engine"
        )
        layout.addWidget(build_labeled_row("Language", self.__language_combo))

    def __on_change_engine(self, index: int) -> None:
        """エンジンが変わったことを外へ知らせる。

        Args:
            index: 選ばれた項目の位置。
        """
        self.on_change_engine_signal.emit(self.engine())

    def engine(self) -> str:
        """選ばれているエンジン名を返す。"""
        return self.__engine_combo.currentData() or ""

    def language(self) -> str | None:
        """選ばれている言語コードを返す。Auto なら None。"""
        language_type: LanguageType = self.__language_combo.currentData()
        return language_type.code or None

    def set_state(self, engine: str, language: str | None) -> None:
        """選択内容を設定する。

        Args:
            engine: エンジン名。一覧に無ければ変えない。
            language: 言語コード。
        """
        select_combo_data(self.__engine_combo, engine)
        select_combo_data(
            self.__language_combo, LanguageType.from_code(language)
        )
