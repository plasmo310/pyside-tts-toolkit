"""プロトコル検証用のダミー runner。

実エンジンと同じ規約に従う:
  - stdout には JSON だけを出す
  - ログは stderr へ
  - ready を出してからリクエストを受ける

本物のモデルを落とさずに JSONL プロトコル・UTF-8・シャットダウンを検証できる。
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import traceback
import wave
from pathlib import Path

SAMPLE_RATE = 24000


def log(msg: str) -> None:
    print(f"[fake] {msg}", file=sys.stderr, flush=True)


def write_silence(path: Path, seconds: float) -> None:
    frames = int(SAMPLE_RATE * seconds)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(struct.pack(f"<{frames}h", *([0] * frames)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--options", default="{}")
    args = parser.parse_args()
    options = json.loads(args.options)

    stdout = sys.stdout
    # 本物の runner と同じく、うっかり print されたログが stdout を汚さないようにする。
    sys.stdout = sys.stderr

    def send(payload: dict) -> None:
        stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        stdout.flush()

    log(f"options={options}")
    # stdout を汚す誘惑を再現: これは stderr へ流れるべき
    print("このログは stderr へ出るはず")

    send({"op": "ready", "model_id": options.get("model_id", "fake-model")})

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if msg.get("op") == "shutdown":
            log("shutdown")
            return 0
        if msg.get("op") != "synthesize":
            send({"id": msg.get("id"), "ok": False, "error": f"未知の op: {msg.get('op')}"})
            continue

        try:
            if options.get("fail_on_text") == msg["text"]:
                raise RuntimeError("テスト用の意図的な失敗")
            # 日本語がそのまま届いているかを長さで確認できるようにする
            log(f"text={msg['text']!r} language={msg['language']!r}")
            seconds = max(0.1, len(msg["text"]) * 0.05)
            write_silence(Path(msg["output_path"]), seconds)
            send(
                {
                    "id": msg["id"],
                    "ok": True,
                    "sample_rate": SAMPLE_RATE,
                    "duration_sec": seconds,
                    "elapsed_sec": 0.01,
                    "echo_text": msg["text"],
                }
            )
        except Exception as exc:  # noqa: BLE001 - 失敗は必ず親へ返す
            send(
                {
                    "id": msg.get("id"),
                    "ok": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
