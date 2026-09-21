"""プロトコル検証用のダミー runner。

本物のモデルを落とさずに JSONL プロトコル・UTF-8・シャットダウンを
検証できるようにする。通信まわりは実エンジンと同じ
`ttstoolkit.engine.runners.interface` を使うので、このテストが通れば
実エンジンの土台も通っていることになる。
"""

from __future__ import annotations

import sys

from ttstoolkit.engine.runners.interface import (
    EngineRunner,
    log,
    serve,
    set_engine_name,
    write_wav_pcm16,
)

set_engine_name("fake")

# ダミー音声のサンプリングレート
SAMPLE_RATE = 24000

# 1 文字あたりの再生時間 (秒)。テキストが届いた長さを確認できる
_SECONDS_PER_CHAR = 0.05

# 最低限の長さ (秒)
_MIN_SECONDS = 0.1


class FakeRunner(EngineRunner):
    """無音を書き出すだけの runner。

    Attributes:
        __options (dict): エンジン固有の設定。
    """

    def __init__(self, options: dict) -> None:
        """設定を読み取る。

        Args:
            options: エンジン固有の設定。
        """
        self.__options = options
        log(f"options={options}")
        # stdout を汚す誘惑を再現する。interface が退避しているので、
        # これは stderr へ流れるはず
        print("this line must go to stderr")

    @property
    def model_id(self) -> str:
        """設定で指定されたモデル識別子。"""
        return str(self.__options.get("model_id", "fake-model"))

    def synthesize(self, message: dict) -> dict:
        """無音を書き出す。

        Args:
            message: 親から届いたリクエスト。

        Returns:
            dict: サンプリングレート・長さ・所要時間。

        Raises:
            RuntimeError: 設定で失敗させるテキストが来たとき。
        """
        if self.__options.get("fail_on_text") == message["text"]:
            raise RuntimeError("deliberate failure for tests")

        # 日本語がそのまま届いているかを長さで確認できるようにする
        log(f"text={message['text']!r} language={message['language']!r}")
        seconds = max(_MIN_SECONDS, len(message["text"]) * _SECONDS_PER_CHAR)
        frames = int(SAMPLE_RATE * seconds)
        write_wav_pcm16(message["output_path"], [0.0] * frames, SAMPLE_RATE)
        return {
            "sample_rate": SAMPLE_RATE,
            "duration_sec": frames / SAMPLE_RATE,
            "elapsed_sec": 0.01,
            "echo_text": message["text"],
        }


if __name__ == "__main__":
    sys.exit(serve(FakeRunner))
