"""エンジンをどう動かすか ── 抽象と、runner をサブプロセスで駆動する実装。

呼ばれる先: core.tts_service のみ (`core` の外からは import しない)
呼ぶ先: core.settings, core.engine, engine._shared.protocol

3 つのモデルは依存ライブラリのピンが互いに排他的で、1 つの仮想環境には
同居できない。そのため実装は必ずプロセス境界をまたぐが、呼ぶ側は
その事情を知らなくてよい ── それが `TTSEngine` の目的。

    with create_engine("irodori") as engine:
        result = engine.synthesize(request)

`__enter__` では `start()` を呼ばない。未対応の言語やパラメータは
`validate()` が弾くので、重いモデルのロード (10〜60 秒) を始める前に
エラーにしたいため。実際の起動は最初の `synthesize()` まで遅延する。

runner はモデルをロードしたまま常駐するので、バッチ処理でロード時間を
毎回払わずに済む。やり取りする中身は
`ttstoolkit.engine._shared.protocol` が定義している。封筒 (op / id / ok)
を組み立てるのは、runner 側の `serve()` とこのモジュールの 2 箇所だけ。

runner 側はモデルのログで stdout を汚さないこと (ログは全て stderr へ)。
その仕掛けは `engine/_shared/runner_base.py` にある。**このモジュールは
そちらを import してはいけない** (import した時点で自分の標準出力まで
差し替わってしまう)。
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from types import TracebackType
from typing import Self

from ttstoolkit.core.engine import (
    Capability,
    EngineNotInstalledError,
    EngineProcessError,
    EngineSpec,
    SynthesisResult,
    UnsupportedLanguageError,
    UnsupportedParameterError,
    get_spec,
)
from ttstoolkit.core.settings import (
    SETUP_SCRIPT,
    SUBPROCESS_FLAGS,
    get_logger,
)
from ttstoolkit.engine._shared.protocol import (
    KEY_ERROR,
    KEY_ID,
    KEY_MODEL_ID,
    KEY_OK,
    KEY_TRACEBACK,
    OP,
    OP_LOG,
    OP_READY,
    OP_SHUTDOWN,
    OP_SYNTHESIZE,
    SynthesisRequest,
    SynthesisResponse,
)

_logger = get_logger(__name__)

# モデルの初回ダウンロードを含むため、起動待ちは長めに取る
_READY_TIMEOUT_SEC = float(os.environ.get("TTS_READY_TIMEOUT", "1800"))
_SYNTH_TIMEOUT_SEC = float(os.environ.get("TTS_SYNTH_TIMEOUT", "900"))
_SHUTDOWN_TIMEOUT_SEC = 20.0

# 失敗時に見せる stderr の行数。全部保持するとメモリを食うので末尾だけ残す
_STDERR_TAIL_LINES = 60


class TTSEngine(ABC):
    """1 つの TTS モデルを扱うインターフェース。

    Attributes:
        spec (EngineSpec): このエンジンの定義。
    """

    def __init__(self, spec: EngineSpec) -> None:
        """エンジンを作る（この時点ではモデルをロードしない）。

        Args:
            spec: このエンジンの定義。
        """
        self.spec = spec

    @property
    def name(self) -> str:
        """エンジン名。"""
        return self.spec.name

    @property
    def model_id(self) -> str:
        """既定で使うモデルの識別子。"""
        return self.spec.model_id

    @abstractmethod
    def start(self) -> None:
        """モデルをロードし、合成を受け付けられる状態にする。"""

    @abstractmethod
    def close(self) -> None:
        """資源を解放する。多重呼び出しは安全であること。"""

    @abstractmethod
    def _synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """検証済みリクエストを実際に合成する。サブクラスが実装する。

        Args:
            request: 検証済みの合成リクエスト。

        Returns:
            SynthesisResult: 合成結果。
        """

    def validate(self, request: SynthesisRequest) -> None:
        """対応できないリクエストを、プロセスを起動する前に弾く。

        Args:
            request: 合成リクエスト。

        Raises:
            UnsupportedLanguageError: 対応していない言語のとき。
            UnsupportedParameterError: 対応していない指定があるとき。
            FileNotFoundError: 参照音声が見つからないとき。
        """
        spec = self.spec

        if request.language and request.language not in spec.languages:
            raise UnsupportedLanguageError(
                f"Engine '{spec.name}' does not support language "
                f"'{request.language}' "
                f"(supported: {', '.join(spec.languages)})"
            )

        if request.reference_audio:
            if not spec.supports(Capability.CLONE):
                raise UnsupportedParameterError(
                    f"Engine '{spec.name}' does not support voice cloning "
                    "from a reference audio"
                )
            if not os.path.isfile(request.reference_audio):
                raise FileNotFoundError(
                    f"Reference audio not found: {request.reference_audio}"
                )

        if request.voice_design and not spec.supports(Capability.VOICE_DESIGN):
            raise UnsupportedParameterError(
                f"Engine '{spec.name}' does not support voice design; "
                "use a reference audio instead"
            )

        if request.speed != 1.0 and not spec.supports(Capability.SPEED):
            raise UnsupportedParameterError(
                f"Engine '{spec.name}' does not support speed "
                f"(speed={request.speed}); leave it at 1.0"
            )

        if request.seed is not None and not spec.supports(Capability.SEED):
            raise UnsupportedParameterError(
                f"Engine '{spec.name}' does not support a fixed seed"
            )

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """1 件を合成する。

        Args:
            request: 合成リクエスト。

        Returns:
            SynthesisResult: 合成結果。

        Raises:
            TTSToolkitError: 検証に失敗した、または合成が失敗したとき。
        """
        self.validate(request)
        directory = os.path.dirname(os.path.abspath(request.output_path))
        os.makedirs(directory, exist_ok=True)
        return self._synthesize(request)

    def __enter__(self) -> Self:
        """with 文に入る。ここではまだモデルをロードしない。"""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """with 文を抜ける。プロセスを確実に終了させる。"""
        self.close()


class SubprocessEngine(TTSEngine):
    """エンジンの仮想環境で runner を起動して合成を委譲する。

    Attributes:
        __process (subprocess.Popen | None): 常駐中の runner。
        __stderr_tail (deque[str]): runner の stderr の末尾。
        __stderr_thread (threading.Thread | None): stderr を読む番。
        __next_id (int): 次に使うリクエスト ID。
        __verbose (bool): runner の stderr をそのままログへ流すか。
        __ready_model_id (str | None): runner が申告したモデル識別子。
    """

    def __init__(self, spec: EngineSpec, verbose: bool = False) -> None:
        """エンジンを作る（この時点では起動しない）。

        Args:
            spec: このエンジンの定義。
            verbose: runner の stderr をそのままログへ流すか。
        """
        super().__init__(spec)
        self.__process: subprocess.Popen | None = None
        self.__stderr_tail: deque[str] = deque(maxlen=_STDERR_TAIL_LINES)
        self.__stderr_thread: threading.Thread | None = None
        self.__next_id = 0
        self.__verbose = verbose
        self.__ready_model_id: str | None = None

    # ------------------------------------------------------------------
    # 起動
    # ------------------------------------------------------------------

    def start(self) -> None:
        """runner を起動し、ready が返るまで待つ。

        Raises:
            EngineNotInstalledError: 仮想環境が構築されていないとき。
            EngineProcessError: 起動に失敗したとき。
        """
        if self.__process is not None:
            return

        spec = self.spec
        if not spec.installed:
            raise EngineNotInstalledError(
                f"Engine '{spec.name}' is not set up yet: {spec.python}\n"
                f"Run {SETUP_SCRIPT} (see {spec.setup_doc_path})"
            )

        command = [
            spec.python,
            "-m",
            spec.runner,
            "--options",
            json.dumps(spec.options),
        ]
        _logger.debug("Starting runner: %s", " ".join(command))
        try:
            self.__process = subprocess.Popen(
                command,
                cwd=spec.cwd,
                env=self.__build_env(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                # GUI から起動したときにコンソール窓を出さない
                creationflags=SUBPROCESS_FLAGS,
            )
        except OSError as e:
            raise EngineProcessError(
                f"Could not start the runner for '{spec.name}': {e}"
            ) from e

        # stderr は別スレッドで読み続ける。読まないとパイプが詰まって
        # 子プロセスが固まる。
        self.__stderr_thread = threading.Thread(
            target=self.__drain_stderr,
            name=f"{spec.name}-stderr",
            daemon=True,
        )
        self.__stderr_thread.start()
        self.__await_ready()

    def __build_env(self) -> dict[str, str]:
        """runner プロセスに渡す環境変数を組み立てる。

        Returns:
            dict[str, str]: 子プロセス用の環境変数。
        """
        env = os.environ.copy()
        # 標準入出力を UTF-8 に固定する。Windows の既定は cp932 で、
        # 日本語テキストをそのまま渡すと確実に壊れる。
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        # runner は別の仮想環境で動くので ttstoolkit を検索パスで渡す。
        # コード側から sys.path を書き換えないための仕掛け。
        search_path = list(self.spec.python_path)
        existing = env.get("PYTHONPATH")
        if existing:
            search_path.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(search_path)
        return env

    def __drain_stderr(self) -> None:
        """runner の stderr を読み続け、末尾を保持する。"""
        process = self.__process
        if process is None or process.stderr is None:
            return
        try:
            for raw_line in process.stderr:
                line = raw_line.rstrip("\n")
                self.__stderr_tail.append(line)
                if self.__verbose:
                    _logger.info("[%s] %s", self.spec.name, line)
        except (ValueError, OSError):
            # close() でストリームが閉じられた場合。終了処理の一部。
            pass

    def __await_ready(self) -> None:
        """runner が ready を返すまで待つ。

        Raises:
            EngineProcessError: ready 以外が返ってきたとき。
        """
        deadline = time.monotonic() + _READY_TIMEOUT_SEC
        while True:
            message = self.__read_message(deadline, "startup")
            if message.get(OP) == OP_READY:
                self.__ready_model_id = (
                    message.get(KEY_MODEL_ID) or self.spec.model_id
                )
                _logger.info(
                    "Engine %s is ready (%s)",
                    self.spec.name,
                    self.__ready_model_id,
                )
                return
            if message.get(OP) == OP_LOG:
                continue
            raise EngineProcessError(
                f"Unexpected response before ready: {message}"
            )

    # ------------------------------------------------------------------
    # 合成
    # ------------------------------------------------------------------

    def _synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """検証済みリクエストを runner に投げて結果を受け取る。

        Args:
            request: 検証済みの合成リクエスト。

        Returns:
            SynthesisResult: 合成結果。

        Raises:
            EngineProcessError: 合成が失敗したとき。
        """
        if self.__process is None:
            self.start()

        self.__next_id += 1
        request_id = self.__next_id
        self.__write_message(
            {OP: OP_SYNTHESIZE, KEY_ID: request_id, **request.to_json()}
        )

        deadline = time.monotonic() + _SYNTH_TIMEOUT_SEC
        while True:
            message = self.__read_message(deadline, "synthesis")
            if message.get(OP) == OP_LOG:
                continue
            if message.get(KEY_ID) != request_id:
                actual = message.get(KEY_ID)
                raise EngineProcessError(
                    f"Response id mismatch (expected {request_id}, "
                    f"got {actual})"
                )
            break

        if not message.get(KEY_OK):
            detail = (
                message.get(KEY_TRACEBACK)
                or message.get(KEY_ERROR)
                or "(no detail)"
            )
            raise EngineProcessError(
                f"Synthesis failed on {self.spec.name}:\n{detail}"
            )

        if not os.path.isfile(request.output_path):
            raise EngineProcessError(
                "The runner reported success but wrote no file: "
                f"{request.output_path}"
            )

        try:
            response = SynthesisResponse.from_json(message)
        except ValueError as e:
            raise EngineProcessError(
                f"Engine {self.spec.name} returned a broken response: {e}"
            ) from e

        return SynthesisResult(
            output_path=request.output_path,
            sample_rate=response.sample_rate,
            duration_sec=response.duration_sec,
            engine=self.spec.name,
            # Qwen のようにリクエスト内容でモデルを切り替えるエンジンは、
            # 応答で実際に使ったモデルを返す。無ければ起動時の申告を使う。
            model_id=(
                response.model_id
                or self.__ready_model_id
                or self.spec.model_id
            ),
            elapsed_sec=response.elapsed_sec,
        )

    # ------------------------------------------------------------------
    # 低レベル入出力
    # ------------------------------------------------------------------

    def __write_message(self, message: dict) -> None:
        """1 行の JSON を runner へ送る。

        Args:
            message: 送る内容。

        Raises:
            EngineProcessError: 書き込みに失敗したとき。
        """
        process = self.__process
        if process is None or process.stdin is None:
            raise EngineProcessError("The runner is not running")
        try:
            process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, ValueError, OSError) as e:
            raise EngineProcessError(
                f"Could not write to the runner.{self.__stderr_report()}"
            ) from e

    def __read_message(self, deadline: float, phase: str) -> dict:
        """runner から 1 行読んで JSON として解釈する。

        Args:
            deadline: この時刻を過ぎたら打ち切る (time.monotonic 基準)。
            phase: エラーメッセージに出す局面の名前。

        Returns:
            dict: 受け取った内容。

        Raises:
            EngineProcessError: 読み取りや解釈に失敗したとき。
        """
        process = self.__process
        if process is None or process.stdout is None:
            raise EngineProcessError("The runner is not running")

        line = self.__read_line(process, deadline, phase)
        try:
            return json.loads(line)
        except json.JSONDecodeError as e:
            raise EngineProcessError(
                "The runner wrote non-JSON to stdout "
                f"(logs must go to stderr): {line[:400]!r}"
                f"{self.__stderr_report()}"
            ) from e

    def __read_line(
        self, process: subprocess.Popen, deadline: float, phase: str
    ) -> str:
        """runner の stdout から 1 行読む。

        Windows ではパイプの読み取りに直接タイムアウトを掛けられないので、
        読み取り自体をスレッドへ逃がして join のタイムアウトで打ち切る。

        Args:
            process: 読み取り対象のプロセス。
            deadline: この時刻を過ぎたら打ち切る。
            phase: エラーメッセージに出す局面の名前。

        Returns:
            str: 読み取った 1 行 (改行と前後の空白は落とす)。

        Raises:
            EngineProcessError: タイムアウト、または runner が落ちたとき。
        """
        result: list[str] = []
        error: list[BaseException] = []

        def read() -> None:
            try:
                result.append(process.stdout.readline())
            except BaseException as e:  # noqa: BLE001
                error.append(e)

        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        thread.join(timeout=max(1.0, deadline - time.monotonic()))

        if thread.is_alive():
            self.__kill()
            raise EngineProcessError(
                f"Engine {self.spec.name} timed out during {phase}."
                f"{self.__stderr_report()}"
            )
        if error:
            raise EngineProcessError(
                f"Could not read from the runner.{self.__stderr_report()}"
            ) from error[0]

        line = result[0] if result else ""
        if line == "":
            raise EngineProcessError(
                f"The runner for {self.spec.name} exited during {phase} "
                f"(exit={process.poll()}).{self.__stderr_report()}"
            )
        return line.strip()

    def __stderr_report(self) -> str:
        """失敗したときに添える runner の stderr の末尾を作る。"""
        if not self.__stderr_tail:
            return " (the runner wrote nothing to stderr)"
        joined = "\n".join(self.__stderr_tail)
        return f"\n--- {self.spec.name} stderr (tail) ---\n{joined}\n---"

    # ------------------------------------------------------------------
    # 終了
    # ------------------------------------------------------------------

    def close(self) -> None:
        """runner を終了させる。多重に呼んでも安全。"""
        process = self.__process
        if process is None:
            return
        self.__process = None

        try:
            if process.poll() is None and process.stdin is not None:
                with contextlib.suppress(BrokenPipeError, ValueError, OSError):
                    process.stdin.write(json.dumps({OP: OP_SHUTDOWN}) + "\n")
                    process.stdin.flush()
                    process.stdin.close()
            try:
                process.wait(timeout=_SHUTDOWN_TIMEOUT_SEC)
            except subprocess.TimeoutExpired:
                process.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=5)
        finally:
            if self.__stderr_thread is not None:
                self.__stderr_thread.join(timeout=2)
                self.__stderr_thread = None
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    with contextlib.suppress(OSError):
                        stream.close()

    def __kill(self) -> None:
        """runner を即座に落とす (タイムアウトしたとき用)。"""
        process = self.__process
        self.__process = None
        if process is not None and process.poll() is None:
            process.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=5)


def create_engine(name: str, verbose: bool = False) -> TTSEngine:
    """エンジン名から `TTSEngine` を作る。呼び出し側は with 文で使う。

    将来 HTTP バックエンド (Irodori-TTS-Server のような OpenAI 互換
    サーバ) を足す場合は、ここに分岐を 1 つ増やすだけで済む。
    呼び出し側と `TTSEngine` のインターフェースは変わらない。

    Args:
        name: エンジン名。
        verbose: runner の stderr をそのままログへ流すか。

    Returns:
        TTSEngine: 生成したエンジン。

    Raises:
        EngineNotFoundError: 定義されていない名前のとき。
    """
    return SubprocessEngine(get_spec(name), verbose=verbose)
