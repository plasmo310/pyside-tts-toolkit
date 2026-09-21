"""ツールの設定 ── GUI の見た目・保存先・リソースのパス。

呼ばれる先: main.py, gui/
呼ぶ先: core.paths, core.settings

どのモデルをどの仮想環境で動かすかの定義 (`ENGINE_DEFINITIONS`) と、
名前からの引き当て (`get_spec` など) は `core.engine` にある。
画面に並べる選択肢は `definitions.py`。
"""

from __future__ import annotations

import os
import sys

from ttstoolkit.core.paths import ROOT_DIR
from ttstoolkit.core.settings import IS_WINDOWS

# スタイルシートの中で resources/ の絶対パスに置き換えるプレースホルダ
_RESOURCES_DIR_PLACEHOLDER = "{RESOURCES_DIR}"


class ToolConfig:
    """ツール設定クラス"""

    # ツールタイトル
    TOOL_TITLE = "TTS Toolkit"

    # ウィンドウの既定サイズ
    WINDOW_WIDTH = 1000
    WINDOW_HEIGHT = 880

    # 入力行の高さ (全部揃えて縦位置をきれいに出す)
    ROW_HEIGHT = 28

    # Cancel / Run ボタンの幅
    # 高さはタブと揃えるため stylesheet.qss 側で指定している
    CANCEL_BUTTON_WIDTH = 110

    # 入力行の左に置くラベルの幅 (タブ間で揃える)
    LABEL_WIDTH = 150

    # 台詞やボイス指示を書き込む複数行入力の高さ。
    # 1 タブに 2 つ並ぶので、全部の行が一度に見える高さに抑える。
    TEXT_EDIT_HEIGHT = 84

    # QSettings の識別子
    SETTINGS_ORGANIZATION = "TTSToolkit"
    SETTINGS_APPLICATION = "TTSToolkit"

    # 参照音声の選択ダイアログのフィルタ
    AUDIO_FILE_FILTER = "Audio (*.wav *.mp3 *.flac *.ogg);;All Files (*)"

    # 台本ファイル選択ダイアログのフィルタ
    SCRIPT_FILE_FILTER = "Text (*.txt);;All Files (*)"

    # キャスト定義ファイル選択ダイアログのフィルタ
    CAST_FILE_FILTER = "TOML (*.toml);;All Files (*)"

    @staticmethod
    def __get_resources_dir() -> str:
        """resources/ の絶対パスを返す。

        PyInstaller で固めた場合は `_internal/resources/` を見る。
        参考: https://pyinstaller.org/en/stable/runtime-information.html
        """
        if hasattr(sys, "_MEIPASS"):
            return os.path.join(sys._MEIPASS, "resources")
        return os.path.join(ROOT_DIR, "resources")

    @staticmethod
    def get_tool_icon_path() -> str:
        """ツールアイコンのパスを返す。

        置いていなければ空文字を返す (Qt は既定のアイコンを使う)。

        Returns:
            str: アイコンのパス。無ければ空文字。
        """
        file_name = (
            "tool_icon_rect.ico" if IS_WINDOWS else "tool_icon_round.icns"
        )
        path = os.path.join(
            ToolConfig.__get_resources_dir(), "icon", file_name
        )
        return path if os.path.isfile(path) else ""

    @staticmethod
    def load_stylesheet() -> str:
        """スタイルシートを読み込む。

        QSS の `url()` は実行時のカレントディレクトリ基準で解決されて
        しまうので、`{RESOURCES_DIR}` を resources/ の絶対パスに
        置き換えてから返す。区切りは QSS が解釈できるスラッシュにする。

        Returns:
            str: スタイルシートの中身。読めなければ空文字。
        """
        resources_dir = ToolConfig.__get_resources_dir()
        stylesheet_path = os.path.join(resources_dir, "ui", "stylesheet.qss")
        if not os.path.isfile(stylesheet_path):
            return ""

        try:
            with open(stylesheet_path, encoding="utf-8") as file:
                stylesheet = file.read()
        except UnicodeDecodeError:
            with open(stylesheet_path, encoding="utf-8-sig") as file:
                stylesheet = file.read()

        return stylesheet.replace(
            _RESOURCES_DIR_PLACEHOLDER, resources_dir.replace("\\", "/")
        )
