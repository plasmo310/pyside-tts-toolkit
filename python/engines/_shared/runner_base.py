"""3 つの runner が共有するプロトコル実装。

各エンジンの venv は互いに独立していて共通層（tts_sample）を import できない。
そのため依存ゼロのこのファイルを sys.path 経由で共有する。

重要: このモジュールは **torch を import する前に** import すること。
import 時点で sys.stdout を stderr へ差し替え、本物のハンドルを退避する。
transformers / huggingface_hub / tqdm がうっかり stdout に出しても
JSONL プロトコルが壊れないようにするための措置。
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import traceback
import wave

# 本物の stdout を退避し、以後 print() は stderr へ流す。
_CHANNEL = sys.stdout
sys.stdout = sys.stderr

ENGINE_NAME = "engine"


def set_engine_name(name: str) -> None:
    global ENGINE_NAME  # noqa: PLW0603 - runner 全体で使うログの接頭辞
    ENGINE_NAME = name


def log(message: str) -> None:
    print(f"[{ENGINE_NAME}] {message}", file=sys.stderr, flush=True)


def send(payload: dict) -> None:
    _CHANNEL.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _CHANNEL.flush()


def parse_options() -> dict:
    parser = argparse.ArgumentParser()
    parser.add_argument("--options", default="{}")
    args = parser.parse_args()
    return json.loads(args.options)


def write_wav_pcm16(path: str, samples, sample_rate: int) -> int:
    """モノラル 16bit PCM の WAV を書き、フレーム数を返す。

    エンジンごとに float32 WAV だったり 24/48kHz だったりすると、下流
    （Remotion、音声編集、Python の wave モジュール）で扱いが揃わない。
    出力形式は PCM16 に統一する。サンプリングレートはモデル本来の値を保つ。

    ``samples`` は 1 次元の float 配列（numpy 配列・torch テンソル・リスト）。
    値域 [-1, 1] を想定し、範囲外はクリップする。
    """
    # torch テンソル / numpy 配列 / リストのいずれでも受ける。
    if hasattr(samples, "detach"):  # torch.Tensor
        samples = samples.detach().to("cpu").flatten().tolist()
    elif hasattr(samples, "reshape"):  # numpy.ndarray
        samples = samples.reshape(-1).tolist()
    else:
        samples = list(samples)

    frames = len(samples)
    if frames == 0:
        raise ValueError("生成された音声が空です。")

    pcm = bytearray(frames * 2)
    struct.pack_into(
        f"<{frames}h",
        pcm,
        0,
        *(max(-32768, min(32767, round(float(s) * 32767.0))) for s in samples),
    )

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(pcm))
    return frames


def serve(build_runner) -> int:
    """runner を組み立てて JSONL のループを回す。

    ``build_runner(options)`` は次を備えたオブジェクトを返すこと:
      - ``model_id``: str
      - ``synthesize(message: dict) -> dict``
        （``sample_rate`` / ``duration_sec`` / ``elapsed_sec`` を含む dict）
    """
    options = parse_options()

    try:
        runner = build_runner(options)
    except Exception as exc:  # noqa: BLE001 - 起動失敗も親へ伝える
        log(traceback.format_exc())
        send({"op": "fatal", "error": str(exc)})
        return 1

    send({"op": "ready", "model_id": runner.model_id})

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            log(f"JSON として読めない入力を無視しました: {line[:200]!r}")
            continue

        op = message.get("op")
        if op == "shutdown":
            log("shutdown を受け取りました。")
            return 0
        if op != "synthesize":
            send({"id": message.get("id"), "ok": False, "error": f"未知の op: {op}"})
            continue

        try:
            result = runner.synthesize(message)
            send({"id": message["id"], "ok": True, **result})
        except Exception as exc:  # noqa: BLE001 - 1 件の失敗で常駐を止めない
            log(traceback.format_exc())
            send(
                {
                    "id": message.get("id"),
                    "ok": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
    return 0
