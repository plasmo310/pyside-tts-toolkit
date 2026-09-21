"""TTS Toolkit (GUI) の起点。

    scripts\\win\\LaunchApp.bat

または共通層の仮想環境で

    .venvs\\common\\Scripts\\python.exe -m ttstoolkit.main

で起動する。合成そのものは CLI と同じ `ttstoolkit.engine` を呼ぶだけ
なので、画面から実行できることと CLI から実行できることは常に一致する。
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ttstoolkit.gui.main_controller import MainController
from ttstoolkit.tool_config import ToolConfig


def main() -> int:
    """メイン処理

    Returns:
        int: プロセスの終了コード。
    """
    app = QApplication(sys.argv)
    icon_path = ToolConfig.get_tool_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    app.setStyle("Fusion")
    stylesheet = ToolConfig.load_stylesheet()
    if stylesheet:
        app.setStyleSheet(stylesheet)

    controller = MainController()
    controller.launch()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
