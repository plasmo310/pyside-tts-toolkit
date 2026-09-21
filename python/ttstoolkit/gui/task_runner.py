"""時間のかかる GUI 処理を別スレッドで回すワーカー。

合成はモデルのダウンロードを含めると数分かかることがあるので、GUI
スレッドでは回さない。キャンセルは協調式で、次の 1 件に入る前に
止まる (生成中の 1 件は最後まで走る)。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6 import QtCore

from ttstoolkit.core.settings import ROOT_LOGGER_NAME, TTSToolkitError

# 進捗を流す関数とキャンセル判定の関数を受け取り、結果を返す処理
TaskFunc = Callable[[Callable[[str], None], Callable[[], bool]], Any]


class TaskRunner(QtCore.QThread):
    """時間のかかる処理を 1 回だけ別スレッドで回すワーカー。

    Attributes:
        __task (TaskFunc): 実行する処理。
        __is_canceled (bool): Cancel が押されたか。
    """

    on_progress_signal = QtCore.Signal(str)
    on_finished_signal = QtCore.Signal(object)
    on_error_signal = QtCore.Signal(str)

    def __init__(
        self, task: TaskFunc, parent: QtCore.QObject | None = None
    ) -> None:
        """ワーカーを作る（この時点では走らせない）。

        Args:
            task: 進捗を流す関数とキャンセル判定の関数を受け取り、
                結果を返す処理。
            parent: 親オブジェクト。
        """
        super().__init__(parent)
        self.__task = task
        self.__is_canceled = False

    def cancel(self) -> None:
        """キャンセルを要求する。

        合成のループは、次の 1 件に入る前に止まる。
        """
        self.__is_canceled = True

    def run(self) -> None:
        """別スレッドで処理を実行し、結果か失敗を emit する。"""
        try:
            outcome = self.__task(
                self.on_progress_signal.emit, lambda: self.__is_canceled
            )
        except TTSToolkitError as e:
            # 利用者に見せてよい文言なのでそのまま出す
            self.on_error_signal.emit(str(e))
        except Exception as e:
            logging.getLogger(ROOT_LOGGER_NAME).exception("Task failed")
            self.on_error_signal.emit(f"{type(e).__name__}: {e}")
        else:
            self.on_finished_signal.emit(outcome)
