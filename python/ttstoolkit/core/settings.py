"""実行環境まわり: OS 差分・例外・ロガー。

音声合成とも台本の解釈とも無関係な、プロジェクト全体の土台。
`core` の最下層で、ここは何も import しない。

呼ばれる先: cli/, gui/, logger.py, core の全部
呼ぶ先: なし

Attributes:
    IS_WINDOWS (bool): Windows で動いているか。
    SETUP_SCRIPT (str): エンジン環境を作るスクリプトのパス (OS 別)。
    SUBPROCESS_FLAGS (int): 子プロセスを起動するときの creationflags。
    ROOT_LOGGER_NAME (str): このツールのロガー名前空間の根。
"""

from __future__ import annotations

import logging
import os
import subprocess

# OS ごとに案内する手順もパスの組み立ても違うのでここで一度だけ振り分ける
IS_WINDOWS = os.name == "nt"
SETUP_SCRIPT = (
    "scripts\\win\\SetupEngines.ps1"
    if IS_WINDOWS
    else "scripts/setup_engines.sh"
)

# GUI は pythonw.exe (コンソールを持たない) から起動するため、素直に
# 子プロセスを作るとエンジンごとに黒いコンソール窓が開いてしまう。
# Windows では CREATE_NO_WINDOW を付けて抑える。他の OS にこの定数は
# 無いので 0 (= 指定しないのと同じ) になる。
SUBPROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ルートロガーではなくこの名前空間を使う。ルートにハンドラを付けると
# torch や huggingface_hub 自身のログまで拾ってしまうため。
ROOT_LOGGER_NAME = "ttstoolkit"


class TTSToolkitError(Exception):
    """このツール由来のエラー。

    core 配下は `sys.exit()` せずにこれを投げ、終了コードの決定と
    画面表示は呼び出し側 (CLI / GUI) に任せる。こうしておくと GUI から
    呼んだときにプロセスが落ちず、メッセージをダイアログに出せる。
    """


def get_logger(name: str) -> logging.Logger:
    """`ttstoolkit.<name>` のロガーを返す。`__name__` を渡す。"""
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
