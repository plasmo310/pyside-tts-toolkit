"""runner の共通インターフェースと、親プロセスとの通信。

runner はエンジンごとの仮想環境で動く小さなプログラムで、モデルを
ロードしたまま常駐し、標準入出力の JSONL で合成を受け付ける。
プロトコルの説明は `engine/subprocess_engine.py` にある。

3 つの runner はこの `EngineRunner` を実装する。`serve()` に渡せば
通信・エラー処理・終了はすべてここが引き受けるので、各 runner は
「モデルをロードして 1 件合成する」ことだけを書けばよい。

**重要**: このモジュールは import された時点で `sys.stdout` を
`sys.stderr` に差し替え、本物のハンドルを退避する。transformers /
huggingface_hub / tqdm がうっかり stdout に出しても JSONL が壊れない
ようにするための措置で、**torch より先に import する**必要がある。
そのため各 runner は torch やモデルのライブラリを関数の中で import
している (モジュールの先頭で import すると並べ替えで順序が崩れる)。
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import traceback
import wave
from abc import ABC, abstractmethod
from collections.abc import Callable

# 本物の stdout を退避し、以後 print() は stderr へ流す
_CHANNEL = sys.stdout
sys.stdout = sys.stderr

# ログの行頭に付けるエンジン名
_engine_name = "engine"

# 音声の値域。範囲外はクリップして 16bit PCM に収める
_PCM16_MAX = 32767
_PCM16_MIN = -32768


class EngineRunner(ABC):
    """1 つの TTS モデルを常駐させて合成する runner のインターフェース。

    実装クラスはコンストラクタでモデルをロードし、`synthesize()` で
    1 件ぶんの合成を行う。例外はそのまま投げてよい (`serve()` が
    捕まえて親プロセスへ返す)。
    """

    @property
    @abstractmethod
    def model_id(self) -> str:
        """ロードしたモデルの識別子。起動時に親へ申告する。"""

    @abstractmethod
    def synthesize(self, message: dict) -> dict:
        """1 件を合成して wav を書き出す。

        Args:
            message: 親から届いたリクエスト。`text` と `output_path` は
                必ず入っている。

        Returns:
            dict: `sample_rate` / `duration_sec` / `elapsed_sec` を含む
                辞書。実際に使ったモデルが既定と違うときは `model_id`
                も入れる。
        """


def set_engine_name(name: str) -> None:
    """ログの行頭に付けるエンジン名を設定する。

    Args:
        name: エンジン名。
    """
    global _engine_name
    _engine_name = name


def log(message: str) -> None:
    """進捗を標準エラーへ 1 行出す。

    stdout は JSONL の通信路なので、ログは必ずこちらへ出す。

    Args:
        message: 出力する文字列。
    """
    print(f"[{_engine_name}] {message}", file=sys.stderr, flush=True)


def send(payload: dict) -> None:
    """1 行の JSON を親プロセスへ送る。

    Args:
        payload: 送る内容。
    """
    _CHANNEL.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _CHANNEL.flush()


def parse_options() -> dict:
    """起動引数の `--options` を解釈する。

    Returns:
        dict: エンジン固有の設定 (`tool_config.ENGINE_DEFINITIONS`)。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--options", default="{}")
    return json.loads(parser.parse_args().options)


def write_wav_pcm16(path: str, samples: object, sample_rate: int) -> int:
    """モノラル 16bit PCM の WAV を書き、フレーム数を返す。

    エンジンごとに float32 WAV だったり 24/48kHz だったりすると、
    下流 (動画編集、Python の wave モジュール) で扱いが揃わない。
    出力形式は PCM16 に統一し、サンプリングレートだけモデル本来の
    値を保つ。

    Args:
        path: 書き出す wav のパス。
        samples: 1 次元の float 配列 (torch.Tensor / numpy 配列 /
            リストのいずれか)。値域 [-1, 1] を想定する。
        sample_rate: サンプリングレート (Hz)。

    Returns:
        int: 書き出したフレーム数。

    Raises:
        ValueError: 音声が空のとき。
    """
    if hasattr(samples, "detach"):  # torch.Tensor
        values = samples.detach().to("cpu").flatten().tolist()
    elif hasattr(samples, "reshape"):  # numpy.ndarray
        values = samples.reshape(-1).tolist()
    else:
        values = list(samples)

    frames = len(values)
    if frames == 0:
        raise ValueError("The model returned no audio")

    pcm = bytearray(frames * 2)
    struct.pack_into(
        f"<{frames}h",
        pcm,
        0,
        *(
            max(_PCM16_MIN, min(_PCM16_MAX, round(float(v) * _PCM16_MAX)))
            for v in values
        ),
    )

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(bytes(pcm))
    return frames


def serve(build_runner: Callable[[dict], EngineRunner]) -> int:
    """runner を組み立てて JSONL のループを回す。

    Args:
        build_runner: 設定を受け取って `EngineRunner` を返す関数。
            実装クラスそのものを渡せばよい。

    Returns:
        int: プロセスの終了コード。
    """
    options = parse_options()

    try:
        runner = build_runner(options)
    except Exception as e:  # noqa: BLE001 - 起動失敗も親へ伝える
        log(traceback.format_exc())
        send({"op": "fatal", "error": str(e)})
        return 1

    send({"op": "ready", "model_id": runner.model_id})

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            log(f"Ignoring a non-JSON line: {line[:200]!r}")
            continue

        operation = message.get("op")
        if operation == "shutdown":
            log("Received shutdown")
            return 0
        if operation != "synthesize":
            send(
                {
                    "id": message.get("id"),
                    "ok": False,
                    "error": f"Unknown op: {operation}",
                }
            )
            continue

        _handle_synthesize(runner, message)
    return 0


def _handle_synthesize(runner: EngineRunner, message: dict) -> None:
    """1 件の合成リクエストを処理して結果を返す。

    1 件の失敗で常駐を止めないよう、例外はここで捕まえて親へ返す。

    Args:
        runner: 合成を行う runner。
        message: 親から届いたリクエスト。
    """
    try:
        result = runner.synthesize(message)
    except Exception as e:  # noqa: BLE001 - 1 件の失敗で常駐を止めない
        log(traceback.format_exc())
        send(
            {
                "id": message.get("id"),
                "ok": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
        )
    else:
        send({"id": message["id"], "ok": True, **result})
