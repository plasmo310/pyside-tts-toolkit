"""メイン画面 Model。

`engine` パッケージの API を呼ぶのはこのクラスだけ。Qt のウィジェット
には触らず (保存に `QSettings` を使うだけ)、進捗は渡された関数へ、
失敗は `TTSToolkitError` で返す。CLI の各スクリプトの `main()` に
あたる部分をここに置いている。
"""

from __future__ import annotations

import json
import os
from typing import Any

from PySide6.QtCore import QByteArray, QSettings

from ttstoolkit.engine.jobs import JobOutcome, run_script
from ttstoolkit.engine.paths import SCRIPT_DIR, VOICES_DIR, resolve_input
from ttstoolkit.engine.registry import create_engine, get_spec
from ttstoolkit.engine.script import load_script
from ttstoolkit.engine.settings import TTSToolkitError, get_logger
from ttstoolkit.engine.types import SynthesisRequest, default_output_path
from ttstoolkit.gui.widgets.script_tab import ScriptTabRequest
from ttstoolkit.gui.widgets.synthesis_tab import SynthesisTabRequest
from ttstoolkit.gui.widgets.voice_design_tab import VoiceDesignTabRequest
from ttstoolkit.tool_config import ToolConfig

_logger = get_logger(__name__)


class MainModel:
    """メイン画面 Modelクラス

    Attributes:
        __settings (QSettings): ウィンドウ状態と入力値の保存先。
    """

    __SAVE_KEY_GEOMETRY = "window/geometry"
    __SAVE_KEY_SPLITTER = "window/splitter"
    __SAVE_KEY_TAB_STATE = "state/%s"

    def __init__(self) -> None:
        """モデルを作る（この時点ではモデルをロードしない）。"""
        self.__settings = QSettings(
            ToolConfig.SETTINGS_ORGANIZATION,
            ToolConfig.SETTINGS_APPLICATION,
        )

    # ------------------------------------------------------------------
    # 実行
    # ------------------------------------------------------------------

    def run_synthesis(
        self, request: SynthesisTabRequest, verbose: bool = False
    ) -> JobOutcome:
        """テキストを 1 件合成して書き出す。

        Args:
            request: 画面で指定された実行内容。
            verbose: エンジン自身の出力もログへ流すか。

        Returns:
            JobOutcome: 書き出したパス。

        Raises:
            TTSToolkitError: 入力が足りない、または合成が失敗したとき。
        """
        if not request.text:
            raise TTSToolkitError("Enter the text to speak")

        reference = self.__resolve_reference(request.reference_audio)
        output_path = self.__resolve_output(
            request.output_dir,
            request.output_name,
            default_output_path(
                request.engine, request.text, request.output_dir
            ),
        )

        synthesis = SynthesisRequest(
            text=request.text,
            output_path=output_path,
            language=request.language,
            reference_audio=reference,
            reference_text=request.reference_text,
            voice_design=request.voice_design,
            seed=request.seed,
            speed=request.speed,
        )

        with create_engine(request.engine, verbose=verbose) as engine:
            result = engine.synthesize(synthesis)

        _logger.info(
            "wrote %s (%d Hz / %.2fs)",
            result.output_path,
            result.sample_rate,
            result.duration_sec,
        )
        return JobOutcome(
            written_paths=[result.output_path],
            total_count=1,
        )

    def run_voice_design(
        self, request: VoiceDesignTabRequest, verbose: bool = False
    ) -> JobOutcome:
        """文章から声を作り、試し読みを書き出す。

        Args:
            request: 画面で指定された実行内容。
            verbose: エンジン自身の出力もログへ流すか。

        Returns:
            JobOutcome: 書き出したパス。

        Raises:
            TTSToolkitError: 入力が足りない、または合成が失敗したとき。
        """
        if not request.voice_design:
            raise TTSToolkitError("Describe the voice you want")
        if not request.text:
            raise TTSToolkitError("Enter the sample text to read")

        output_path = self.__resolve_output(
            request.output_dir,
            request.output_name,
            os.path.join(request.output_dir, "master.wav"),
        )

        synthesis = SynthesisRequest(
            text=request.text,
            output_path=output_path,
            language=request.language,
            voice_design=request.voice_design,
            seed=request.seed,
        )

        with create_engine(request.engine, verbose=verbose) as engine:
            result = engine.synthesize(synthesis)

        _logger.info("wrote %s", result.output_path)
        _logger.info(
            "Keep this take and clone from it to reuse the same voice"
        )
        return JobOutcome(
            written_paths=[result.output_path],
            total_count=1,
        )

    def run_script(
        self,
        request: ScriptTabRequest,
        on_progress: object,
        is_canceled: object,
        verbose: bool = False,
    ) -> JobOutcome:
        """台本をまとめて合成して書き出す。

        Args:
            request: 画面で指定された実行内容。
            on_progress: 進捗 1 行ぶんを受け取る関数。
            is_canceled: Cancel が押されたかを返す関数。
            verbose: エンジン自身の出力もログへ流すか。

        Returns:
            JobOutcome: 書き出したパスと失敗の記録。

        Raises:
            TTSToolkitError: 入力が足りない、または台本が読めないとき。
        """
        if not request.cast_path:
            raise TTSToolkitError("Select a cast file")
        if not request.script_path:
            raise TTSToolkitError("Select a script file")

        script = load_script(
            self.__resolve_existing(request.cast_path, "Cast file not found"),
            self.__resolve_existing(
                request.script_path, "Script file not found"
            ),
        )
        _logger.info(
            "%d lines / %d characters / engines: %s",
            len(script.lines),
            len(script.voices_used()),
            ", ".join(script.engines_used()),
        )

        return run_script(
            script=script,
            output_dir=request.output_dir,
            gap_sec=request.gap_sec,
            keep_going=request.keep_going,
            verbose=verbose,
            on_progress=on_progress,
            is_canceled=is_canceled,
        )

    # ------------------------------------------------------------------
    # 入力の解決とヘルパ
    # ------------------------------------------------------------------

    @staticmethod
    def is_engine_installed(engine: str) -> bool:
        """エンジンの仮想環境が構築済みかを返す。

        Args:
            engine: エンジン名。

        Returns:
            bool: 構築済みなら True。
        """
        return get_spec(engine).installed

    @staticmethod
    def engine_setup_doc(engine: str) -> str:
        """エンジンのセットアップ手順のパスを返す。

        Args:
            engine: エンジン名。

        Returns:
            str: `docs/setup/` から始まるパス。
        """
        return f"docs/setup/{get_spec(engine).setup_doc}"

    @staticmethod
    def __resolve_reference(path: str | None) -> str | None:
        """参照音声のパスを解決し、実在することを確かめる。

        Args:
            path: 画面で指定されたパス。

        Returns:
            str | None: 実在が確認できたパス。未指定なら None。

        Raises:
            TTSToolkitError: どこにも見つからないとき。
        """
        if not path:
            return None
        resolved = resolve_input(path, VOICES_DIR)
        if not os.path.isfile(resolved):
            raise TTSToolkitError(f"Reference audio not found: {resolved}")
        return resolved

    @staticmethod
    def __resolve_existing(path: str, missing_message: str) -> str:
        """台本まわりのパスを解決し、実在することを確かめる。

        Args:
            path: 画面で指定されたパス。
            missing_message: 見つからないときの文言。

        Returns:
            str: 実在が確認できたパス。

        Raises:
            TTSToolkitError: どこにも見つからないとき。
        """
        resolved = resolve_input(path, SCRIPT_DIR)
        if not os.path.isfile(resolved):
            raise TTSToolkitError(f"{missing_message}: {resolved}")
        return resolved

    @staticmethod
    def __resolve_output(
        output_dir: str, output_name: str, fallback: str
    ) -> str:
        """書き出し先のパスを決める。

        Args:
            output_dir: 書き出し先ディレクトリ。
            output_name: 書き出すファイル名。空なら fallback を使う。
            fallback: ファイル名が空のときのパス。

        Returns:
            str: 書き出す wav のパス。

        Raises:
            TTSToolkitError: 書き出し先が未指定のとき。
        """
        if not output_dir:
            raise TTSToolkitError("Select an output directory")
        if not output_name:
            return fallback
        if os.path.isabs(output_name):
            return output_name
        return os.path.join(output_dir, output_name)

    # ------------------------------------------------------------------
    # 保存データ
    # ------------------------------------------------------------------

    def clear_settings(self) -> None:
        """保存済みのウィンドウ状態とタブ入力値をすべて消去する。"""
        self.__settings.clear()
        self.__settings.sync()

    def load_window_state(self) -> dict[str, QByteArray] | None:
        """保存済みのウィンドウ状態を返す。未保存の場合は None を返す。"""
        if not self.__settings.contains(self.__SAVE_KEY_GEOMETRY):
            return None
        return {
            "geometry": self.__settings.value(self.__SAVE_KEY_GEOMETRY),
            "splitter": self.__settings.value(self.__SAVE_KEY_SPLITTER),
        }

    def save_window_state(self, window_state: dict[str, QByteArray]) -> None:
        """ウィンドウ状態を保存する。

        Args:
            window_state: `MainView.get_window_state()` の戻り値。
        """
        self.__settings.setValue(
            self.__SAVE_KEY_GEOMETRY, window_state["geometry"]
        )
        self.__settings.setValue(
            self.__SAVE_KEY_SPLITTER, window_state["splitter"]
        )
        self.__settings.sync()

    def load_tab_state(self, tab_key: str) -> dict[str, Any] | None:
        """保存済みのタブ入力値を返す。未保存/壊れていれば None を返す。

        Args:
            tab_key: タブを識別する文字列。

        Returns:
            dict[str, Any] | None: 保存済みの入力値。
        """
        raw = self.__settings.value(self.__SAVE_KEY_TAB_STATE % tab_key)
        if not raw:
            return None
        try:
            state = json.loads(raw)
        except (TypeError, ValueError):
            # 形が変わった後の古い保存データは黙って捨てる
            return None
        return state if isinstance(state, dict) else None

    def save_tab_state(self, tab_key: str, state: dict[str, Any]) -> None:
        """タブの入力値を保存する。

        Args:
            tab_key: タブを識別する文字列。
            state: 保存する入力値。
        """
        self.__settings.setValue(
            self.__SAVE_KEY_TAB_STATE % tab_key,
            json.dumps(state, ensure_ascii=False),
        )
        self.__settings.sync()
