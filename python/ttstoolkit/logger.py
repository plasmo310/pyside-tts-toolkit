"""GUI 用のログ設定。

`engine` パッケージは進捗を `ttstoolkit` 名前空間の `logging` に流すので、
そこに Handler を 1 つ足して Qt のシグナルへ中継する。CLI 側の
`ttstoolkit.cli.common` が標準エラーへ出しているのと同じ役割。
"""

from __future__ import annotations

import logging

from PySide6 import QtCore

from ttstoolkit.engine.settings import ROOT_LOGGER_NAME

# ログレベル -> 行頭に付けるラベル (CLI の [info] / [warn] と揃える)
_LEVEL_LABELS = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warn",
    logging.ERROR: "error",
    logging.CRITICAL: "error",
}


class LogBridge(QtCore.QObject):
    """ログ 1 行を Qt のシグナルに中継するオブジェクト。

    ワーカースレッドから emit しても、Qt が自動でキューイングして
    GUI スレッドに届けてくれる。
    """

    on_log_signal = QtCore.Signal(str)


class _GuiLogHandler(logging.Handler):
    """ログ 1 件を `[info] メッセージ` の形にして画面へ流す Handler。

    Attributes:
        __bridge (LogBridge): シグナルの持ち主。
    """

    def __init__(self, bridge: LogBridge) -> None:
        """Handler を作る。

        Args:
            bridge: シグナルの持ち主。
        """
        super().__init__()
        self.__bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        """レベルのラベルを角括弧で前置した 1 行を emit する。"""
        label = _LEVEL_LABELS.get(record.levelno, record.levelname.lower())
        self.__bridge.on_log_signal.emit(f"[{label}] {record.getMessage()}")


def setup_gui_logger() -> LogBridge:
    """`ttstoolkit` のログを画面へ流すブリッジを作って返す。

    ルートロガーには触らない (Qt や huggingface_hub 自身のログまで
    拾わないため)。

    Returns:
        LogBridge: `on_log_signal` にログが流れてくるブリッジ。
    """
    bridge = LogBridge()
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.handlers.clear()
    logger.addHandler(_GuiLogHandler(bridge))
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return bridge
