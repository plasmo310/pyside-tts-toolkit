"""エンジン venv の runner をサブプロセスとして常駐させ、JSONL で駆動する実装。

3 モデルは transformers / torch のピンが互いに排他的で同一 venv に同居できない。
そのため共通層はプロセス境界越しにモデルを呼ぶ。runner はモデルをロードしたまま
常駐するので、バッチ処理でロード時間（10〜60 秒）を毎回払わずに済む。

プロトコル（1 行 1 JSON、UTF-8）:
    runner -> 親  {"op": "ready", "model_id": "..."}
    親 -> runner  {"op": "synthesize", "id": 1, "text": ..., ...}
    runner -> 親  {"id": 1, "ok": true, "sample_rate": 48000, ...}
    runner -> 親  {"id": 1, "ok": false, "error": "...", "traceback": "..."}
    親 -> runner  {"op": "shutdown"}

runner 側はモデルのログで stdout を汚さないこと（ログは全て stderr へ）。
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from .engine import TTSEngine
from .types import (
    EngineNotInstalledError,
    EngineProcessError,
    EngineSpec,
    SynthesisRequest,
    SynthesisResult,
)

# モデルの初回ダウンロードを含むため、起動待ちは長めに取る。
READY_TIMEOUT_SEC = float(os.environ.get("TTS_SAMPLE_READY_TIMEOUT", "1800"))
SYNTH_TIMEOUT_SEC = float(os.environ.get("TTS_SAMPLE_SYNTH_TIMEOUT", "900"))
SHUTDOWN_TIMEOUT_SEC = 20.0
# 失敗時に見せる stderr の行数。全部保持するとメモリを食うので末尾だけ残す。
STDERR_TAIL_LINES = 60


class SubprocessEngine(TTSEngine):
    """エンジン venv の python で runner.py を起動して合成を委譲する。"""

    def __init__(self, spec: EngineSpec, *, verbose: bool = False) -> None:
        super().__init__(spec)
        self._proc: subprocess.Popen | None = None
        self._stderr_tail: deque = deque(maxlen=STDERR_TAIL_LINES)
        self._stderr_thread: threading.Thread | None = None
        self._next_id = 0
        self._verbose = verbose
        self._ready_model_id: str | None = None

    # ------------------------------------------------------------------ 起動

    def start(self) -> None:
        if self._proc is not None:
            return

        spec = self.spec
        if not spec.python.is_file():
            raise EngineNotInstalledError(
                f"エンジン '{spec.name}' の venv がありません: {spec.python}\n"
                f"セットアップ手順: docs/setup/{spec.setup_doc}"
            )
        if not spec.runner.is_file():
            raise EngineNotInstalledError(f"runner が見つかりません: {spec.runner}")

        env = os.environ.copy()
        # 子プロセスの標準入出力を UTF-8 に固定する。Windows の既定は cp932 で、
        # 日本語テキストをそのまま渡すと確実に壊れる。
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env.update({k: str(v) for k, v in spec.env.items()})

        cmd = [str(spec.python), str(spec.runner), "--options", json.dumps(spec.options)]
        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(spec.cwd),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="replace",
                bufsize=1,  # 行バッファ
            )
        except OSError as exc:
            raise EngineProcessError(f"runner の起動に失敗しました: {cmd}") from exc

        # stderr は別スレッドで読み続ける。読まないとパイプが詰まって子が固まる。
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, name=f"{spec.name}-stderr", daemon=True
        )
        self._stderr_thread.start()

        self._await_ready()

    def _drain_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            for raw_line in proc.stderr:
                line = raw_line.rstrip("\n")
                self._stderr_tail.append(line)
                if self._verbose:
                    print(f"[{self.spec.name}] {line}", file=sys.stderr)
        except (ValueError, OSError):
            # close() でストリームが閉じられた場合。終了処理の一部なので無視する。
            pass

    def _await_ready(self) -> None:
        deadline = time.monotonic() + READY_TIMEOUT_SEC
        while True:
            message = self._read_message(deadline, phase="起動")
            if message.get("op") == "ready":
                self._ready_model_id = message.get("model_id") or self.spec.model_id
                return
            if message.get("op") == "log":
                continue
            raise EngineProcessError(
                f"runner が ready を返す前に予期しない応答をしました: {message}"
            )

    # ------------------------------------------------------------------ 合成

    def _synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        if self._proc is None:
            self.start()

        self._next_id += 1
        request_id = self._next_id
        payload = {"op": "synthesize", "id": request_id, **request.to_payload()}

        started = time.monotonic()
        self._write_message(payload)

        deadline = time.monotonic() + SYNTH_TIMEOUT_SEC
        while True:
            message = self._read_message(deadline, phase="合成")
            if message.get("op") == "log":
                continue
            if message.get("id") != request_id:
                raise EngineProcessError(
                    f"応答の id が一致しません (期待 {request_id}, 実際 {message.get('id')})"
                )
            break

        if not message.get("ok"):
            detail = message.get("traceback") or message.get("error") or "(詳細なし)"
            raise EngineProcessError(f"エンジン '{self.spec.name}' の合成が失敗しました:\n{detail}")

        if not request.output_path.is_file():
            raise EngineProcessError(
                f"runner は成功を報告しましたが出力がありません: {request.output_path}"
            )

        return SynthesisResult(
            output_path=request.output_path,
            sample_rate=int(message["sample_rate"]),
            duration_sec=float(message["duration_sec"]),
            engine=self.spec.name,
            # Qwen のようにリクエスト内容でモデルを切り替えるエンジンは、
            # 応答で実際に使ったモデルを返す。無ければ起動時の申告を使う。
            model_id=message.get("model_id") or self._ready_model_id or self.spec.model_id,
            elapsed_sec=float(message.get("elapsed_sec", time.monotonic() - started)),
        )

    # ------------------------------------------------------------ 低レベル IO

    def _write_message(self, message: dict) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise EngineProcessError("runner プロセスが起動していません。")
        try:
            proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError) as exc:
            raise EngineProcessError(
                f"runner への書き込みに失敗しました。{self._stderr_report()}"
            ) from exc

    def _read_message(self, deadline: float, *, phase: str) -> dict:
        """stdout から 1 行読む。"""
        proc = self._proc
        if proc is None or proc.stdout is None:
            raise EngineProcessError("runner プロセスが起動していません。")

        line = self._readline_with_deadline(proc, deadline, phase)
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise EngineProcessError(
                "runner が JSON 以外を stdout に出力しました"
                "（ログは stderr へ出す必要があります）: "
                f"{line[:400]!r}{self._stderr_report()}"
            ) from exc

    def _readline_with_deadline(self, proc: subprocess.Popen, deadline: float, phase: str) -> str:
        """1 行読む。Windows ではパイプ読み取りに直接タイムアウトを掛けられないため、
        読み取り自体をスレッドへ逃がして join のタイムアウトで打ち切る。
        """
        result: list = []
        error: list = []

        def _read() -> None:
            try:
                result.append(proc.stdout.readline())
            except BaseException as exc:  # noqa: BLE001 - スレッド境界で握り潰さない
                error.append(exc)

        thread = threading.Thread(target=_read, daemon=True)
        thread.start()
        thread.join(timeout=max(1.0, deadline - time.monotonic()))

        if thread.is_alive():
            self._kill()
            raise EngineProcessError(
                f"エンジン '{self.spec.name}' の{phase}がタイムアウトしました。"
                f"{self._stderr_report()}"
            )
        if error:
            raise EngineProcessError(
                f"runner からの読み取りに失敗しました。{self._stderr_report()}"
            ) from error[0]

        line = result[0] if result else ""
        if line == "":
            code = proc.poll()
            raise EngineProcessError(
                f"エンジン '{self.spec.name}' の runner が{phase}中に終了しました"
                f" (exit={code})。{self._stderr_report()}"
            )
        return line.strip()

    def _stderr_report(self) -> str:
        if not self._stderr_tail:
            return " (stderr の出力はありません)"
        joined = "\n".join(self._stderr_tail)
        return f"\n--- {self.spec.name} stderr (末尾) ---\n{joined}\n---"

    # ------------------------------------------------------------------ 終了

    def close(self) -> None:
        proc = self._proc
        if proc is None:
            return
        self._proc = None

        try:
            if proc.poll() is None and proc.stdin is not None:
                try:
                    proc.stdin.write(json.dumps({"op": "shutdown"}) + "\n")
                    proc.stdin.flush()
                    proc.stdin.close()
                except (BrokenPipeError, ValueError, OSError):
                    pass
            try:
                proc.wait(timeout=SHUTDOWN_TIMEOUT_SEC)
            except subprocess.TimeoutExpired:
                proc.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=5)
        finally:
            if self._stderr_thread is not None:
                self._stderr_thread.join(timeout=2)
                self._stderr_thread = None
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    with contextlib.suppress(OSError):
                        stream.close()

    def _kill(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=5)


def resolve_venv_python(venv_dir: Path) -> Path:
    """venv ディレクトリから python 実行ファイルのパスを得る。"""
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"
