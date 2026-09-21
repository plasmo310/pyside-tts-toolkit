"""メイン画面 Controller。

View のシグナルを受けて Model を呼び、結果を View へ返す。合成は
モデルのダウンロードを含めると数分かかることがあるので、実行は
`TaskRunner` に載せて別スレッドで回す。
"""

from __future__ import annotations

import os

from ttstoolkit.core.tts_service import JobOutcome
from ttstoolkit.gui.main_model import MainModel
from ttstoolkit.gui.main_view import MainView
from ttstoolkit.gui.task_runner import TaskFunc, TaskRunner
from ttstoolkit.gui.widgets.script_tab import ScriptTabRequest
from ttstoolkit.gui.widgets.synthesis_tab import SynthesisTabRequest
from ttstoolkit.gui.widgets.voice_design_tab import VoiceDesignTabRequest
from ttstoolkit.logger import setup_gui_logger

# QSettings に入力値を保存するときのタブの識別子
_TAB_KEY_SYNTHESIS = "synthesis"
_TAB_KEY_VOICE_DESIGN = "voice_design"
_TAB_KEY_SCRIPT = "script"

# エンジンが未構築のときに出すダイアログ
_SETUP_DIALOG_TITLE = "Engine Not Set Up"
_SETUP_DIALOG_MESSAGE = (
    'The virtual environment for "{engine}" has not been created yet.\n'
    "Run scripts\\win\\setup_engines.ps1 first (see {doc})."
)

# モデルの初回ダウンロードを知らせるダイアログ
_DOWNLOAD_DIALOG_TITLE = "First Run"
_DOWNLOAD_DIALOG_MESSAGE = (
    "The first run downloads the model weights from Hugging Face, which "
    "can take several minutes and a few GB of disk space.\n\n"
    "Do you want to continue?"
)

_CLEAR_SETTINGS_DIALOG_TITLE = "Clear Saved Settings"
_CLEAR_SETTINGS_DIALOG_MESSAGE = (
    "This will clear the saved window layout and all tab values, then "
    "restore the defaults.\n\nDo you want to continue?"
)


class MainController:
    """メイン画面 Controllerクラス

    Attributes:
        __model (MainModel): メイン画面 Model。
        __view (MainView): メイン画面 View。
        __runner (TaskRunner | None): 実行中のワーカー。
        __is_first_run (bool): この起動でまだ 1 度も実行していないか。
    """

    def __init__(self) -> None:
        """Model と View を作り、繋ぐ。"""
        self.__model = MainModel()
        self.__view = MainView()
        self.__runner: TaskRunner | None = None
        self.__is_first_run = True
        self.__setup_logging()
        self.__setup_connections()
        self.__init_data()

    def launch(self) -> None:
        """ツール起動"""
        self.__view.show()
        window_state = self.__model.load_window_state()
        if window_state:
            self.__view.restore_window_state(window_state)

    def __setup_logging(self) -> None:
        """`ttstoolkit` のログを画面のログ欄へ流す。"""
        self.__log_bridge = setup_gui_logger()
        self.__log_bridge.on_log_signal.connect(self.__view.append_log)

    def __init_data(self) -> None:
        """初期データの設定"""
        for tab_key, tab in (
            (_TAB_KEY_SYNTHESIS, self.__view.synthesis_tab),
            (_TAB_KEY_VOICE_DESIGN, self.__view.voice_design_tab),
            (_TAB_KEY_SCRIPT, self.__view.script_tab),
        ):
            state = self.__model.load_tab_state(tab_key)
            if state:
                tab.set_state(state)

    def __setup_connections(self) -> None:
        """Viewとの接続"""
        self.__view.synthesis_tab.on_click_run_signal.connect(
            self.__on_click_run_synthesis_button
        )
        self.__view.voice_design_tab.on_click_run_signal.connect(
            self.__on_click_run_voice_design_button
        )
        self.__view.script_tab.on_click_run_signal.connect(
            self.__on_click_run_script_button
        )
        for tab in (
            self.__view.synthesis_tab,
            self.__view.voice_design_tab,
            self.__view.script_tab,
        ):
            tab.on_click_cancel_signal.connect(self.__on_click_cancel_button)
        self.__view.on_clear_settings_signal.connect(self.__on_clear_settings)
        self.__view.on_close_window_signal.connect(self.__on_close_window)

    def __on_click_run_synthesis_button(
        self, request: SynthesisTabRequest
    ) -> None:
        """Synthesis タブの Run ボタン押下時処理

        Args:
            request: 画面で指定された実行内容。
        """
        if not self.__confirm_engine(request.engine):
            return
        self.__start_task(
            lambda on_progress, is_canceled: self.__model.run_synthesis(
                request
            )
        )

    def __on_click_run_voice_design_button(
        self, request: VoiceDesignTabRequest
    ) -> None:
        """Voice Design タブの Run ボタン押下時処理

        Args:
            request: 画面で指定された実行内容。
        """
        if not self.__confirm_engine(request.engine):
            return
        self.__start_task(
            lambda on_progress, is_canceled: self.__model.run_voice_design(
                request
            )
        )

    def __on_click_run_script_button(self, request: ScriptTabRequest) -> None:
        """Script タブの Run ボタン押下時処理

        使うエンジンは台本を読むまで分からないので、ここでは未構築の
        確認をせず、Model が投げる例外に任せる。

        Args:
            request: 画面で指定された実行内容。
        """
        if not self.__confirm_first_run():
            return
        self.__start_task(
            lambda on_progress, is_canceled: self.__model.run_script(
                request, on_progress, is_canceled
            )
        )

    def __confirm_engine(self, engine: str) -> bool:
        """エンジンが使える状態かを確かめる。

        Args:
            engine: 使うエンジン名。

        Returns:
            bool: 実行してよければ True。
        """
        if not self.__model.is_engine_installed(engine):
            self.__view.show_error_dialog(
                _SETUP_DIALOG_MESSAGE.format(
                    engine=engine,
                    doc=self.__model.engine_setup_doc(engine),
                )
            )
            return False
        return self.__confirm_first_run()

    def __confirm_first_run(self) -> bool:
        """初回だけ、重みのダウンロードに時間がかかる旨を確認する。

        Returns:
            bool: 実行してよければ True。
        """
        if not self.__is_first_run:
            return True
        if not self.__view.show_confirm_dialog(
            _DOWNLOAD_DIALOG_TITLE, _DOWNLOAD_DIALOG_MESSAGE
        ):
            return False
        self.__is_first_run = False
        return True

    def __on_click_cancel_button(self) -> None:
        """Cancel ボタン押下時処理"""
        if self.__runner is None:
            return
        self.__view.append_log("[info] Canceling...")
        self.__runner.cancel()

    def __start_task(self, task: TaskFunc) -> None:
        """処理を別スレッドで開始する。

        Args:
            task: 実行する処理。
        """
        if self.__runner is not None:
            return

        self.__view.clear_log()
        self.__view.set_running(True)

        self.__runner = TaskRunner(task)
        self.__runner.on_progress_signal.connect(self.__view.append_log)
        self.__runner.on_finished_signal.connect(self.__on_task_finished)
        self.__runner.on_error_signal.connect(self.__on_task_error)
        self.__runner.finished.connect(self.__on_task_stopped)
        self.__runner.start()

    def __on_task_finished(self, outcome: JobOutcome) -> None:
        """処理が終わったときの表示

        Args:
            outcome: 実行結果。
        """
        if outcome.is_canceled:
            self.__view.append_log("[warn] Canceled")
        self.__view.append_log(
            f"[info] Completed ({len(outcome.written_paths)} files)"
        )
        for failure in outcome.failures:
            self.__view.append_log(f"[error] {failure['error']}")

        if not outcome.written_paths:
            return
        output_dir = self.__output_dir_of(outcome)
        if not self.__view.open_output_folder(output_dir):
            self.__view.append_log(
                f"[warn] Could not open the output folder: {output_dir}"
            )

    @staticmethod
    def __output_dir_of(outcome: JobOutcome) -> str:
        """書き出したファイルから出力フォルダを求める。

        Args:
            outcome: 実行結果。

        Returns:
            str: 出力フォルダのパス。
        """
        return os.path.dirname(outcome.written_paths[0])

    def __on_task_error(self, message: str) -> None:
        """処理が失敗したときの表示

        Args:
            message: 表示する文言。
        """
        self.__view.append_log(f"[error] {message}")
        self.__view.show_error_dialog(message)

    def __on_task_stopped(self) -> None:
        """ワーカーのスレッドが終わったときの後始末"""
        self.__runner = None
        self.__view.set_running(False)

    def __on_clear_settings(self) -> None:
        """保存済み設定を消去し、画面を既定値へ戻す。"""
        if not self.__view.show_confirm_dialog(
            _CLEAR_SETTINGS_DIALOG_TITLE, _CLEAR_SETTINGS_DIALOG_MESSAGE
        ):
            return
        self.__model.clear_settings()
        self.__view.reset_settings()
        self.__view.append_log("[info] Saved settings have been cleared")

    def __on_close_window(self) -> None:
        """ウィンドウ終了時処理"""
        if self.__runner is not None:
            self.__runner.cancel()
            self.__runner.wait(3000)
        self.__model.save_window_state(self.__view.get_window_state())
        for tab_key, tab in (
            (_TAB_KEY_SYNTHESIS, self.__view.synthesis_tab),
            (_TAB_KEY_VOICE_DESIGN, self.__view.voice_design_tab),
            (_TAB_KEY_SCRIPT, self.__view.script_tab),
        ):
            self.__model.save_tab_state(tab_key, tab.state())
