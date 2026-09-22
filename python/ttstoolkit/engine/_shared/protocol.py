"""親プロセスと runner のあいだでやり取りするデータ。

このモジュールが**両側が守る契約**そのもの。親（`ttstoolkit.core`）は
これを組み立てて送り、runner（`ttstoolkit.engine.<name>.runner`）は
これを受け取って返す。どちらも同じクラスを使うので、片方だけ形が
変わることがない。

やり取りは 1 行 1 JSON（JSONL）。行の「封筒」は次の形で、中身の
`SynthesisRequest` / `SynthesisResponse` がそこへ展開される。

    親 -> runner  {"op": "synthesize", "id": 1, <リクエスト>}
    親 -> runner  {"op": "shutdown"}
    runner -> 親  {"op": "ready", "model_id": "..."}
    runner -> 親  {"id": 1, "ok": true, <レスポンス>}
    runner -> 親  {"id": 1, "ok": false, "error": "...", "traceback": "..."}

封筒を組み立て／読み取りするのは `_shared/runner_base.py` の `serve()` と
`core/_internal/engine_process.py` の 2 箇所だけにしている。

**このモジュールは stdlib しか import しない。**とくに同じフォルダの
`runner_base` を import してはいけない（あちらは import した時点で
`sys.stdout` を差し替えるので、親側が巻き込まれると標準出力が壊れる）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# 封筒のキー。文字列を直接書かずにここを参照する
OP = "op"
OP_SYNTHESIZE = "synthesize"
OP_SHUTDOWN = "shutdown"
OP_READY = "ready"
OP_LOG = "log"
OP_FATAL = "fatal"

KEY_ID = "id"
KEY_OK = "ok"
KEY_ERROR = "error"
KEY_TRACEBACK = "traceback"
KEY_MODEL_ID = "model_id"


@dataclass(frozen=True)
class SynthesisRequest:
    """1 件の合成リクエスト。親 -> runner。

    `reference_text` は Qwen3-TTS のクローンが参照音声の書き起こしを
    要求するためにある。Chatterbox と Irodori では使われない。未指定の
    場合 Qwen は話者埋め込みのみを使うモードへ落ちる。

    Attributes:
        text: 読み上げるテキスト。
        output_path: 書き出す wav のパス。
        language: 言語コード ("ja" / "en")。None はエンジンの自動判定。
        reference_audio: 声を真似る参照音声のパス。
        reference_text: 参照音声の書き起こし。
        voice_design: 文章による声の指定。
        seed: 乱数シード。
        speed: 話速。1.0 が等倍。
        volume: 音量。1.0 が等倍。書き出し直前に振幅へ掛ける
            だけなので、エンジンを問わず常に対応している。
    """

    text: str
    output_path: str
    language: str | None = None
    reference_audio: str | None = None
    reference_text: str | None = None
    voice_design: str | None = None
    seed: int | None = None
    speed: float = 1.0
    volume: float = 1.0

    def __post_init__(self) -> None:
        """入力を検査し、パスを絶対パスに直す。

        パスを絶対にするのは runner が別のカレントディレクトリで動く
        ため。相対パスのまま渡すと、書き出し先が runner 側の作業
        ディレクトリ基準になって行方不明になる (Irodori は clone の中で
        動かしている)。

        Raises:
            ValueError: テキストが空、speed が 0 以下、または volume が
                負のとき。
        """
        if not self.text.strip():
            raise ValueError("Text is empty")
        if self.speed <= 0:
            raise ValueError(f"Speed must be positive: {self.speed}")
        if self.volume < 0:
            raise ValueError(f"Volume must not be negative: {self.volume}")

        object.__setattr__(
            self, "output_path", os.path.abspath(self.output_path)
        )
        if self.reference_audio:
            object.__setattr__(
                self,
                "reference_audio",
                os.path.abspath(self.reference_audio),
            )

    def to_json(self) -> dict[str, object]:
        """封筒に入れて送れる辞書にする。"""
        return {
            "text": self.text,
            "output_path": self.output_path,
            "language": self.language,
            "reference_audio": self.reference_audio,
            "reference_text": self.reference_text,
            "voice_design": self.voice_design,
            "seed": self.seed,
            "speed": self.speed,
            "volume": self.volume,
        }

    @classmethod
    def from_json(cls, data: dict) -> SynthesisRequest:
        """封筒から取り出した辞書を復元する。

        封筒のキー (`op` / `id`) が混ざっていても無視する。

        Args:
            data: 受け取った 1 行ぶんの辞書。

        Returns:
            SynthesisRequest: 復元したリクエスト。

        Raises:
            ValueError: 必須の項目が無い、または値が不正なとき。
        """
        if "text" not in data or "output_path" not in data:
            raise ValueError("Request needs text and output_path")
        return cls(
            text=str(data["text"]),
            output_path=str(data["output_path"]),
            language=data.get("language"),
            reference_audio=data.get("reference_audio"),
            reference_text=data.get("reference_text"),
            voice_design=data.get("voice_design"),
            seed=data.get("seed"),
            speed=float(data.get("speed") or 1.0),
            volume=(
                float(data["volume"])
                if data.get("volume") is not None
                else 1.0
            ),
        )


@dataclass(frozen=True)
class SynthesisResponse:
    """1 件の合成結果。runner -> 親。

    書き出したパスは親が指定したものなので返さない。親はこれに
    `output_path` とエンジン名を足して `core.engine.SynthesisResult` を
    組み立てる。

    Attributes:
        sample_rate: サンプリングレート (Hz)。
        duration_sec: 音声の長さ (秒)。
        elapsed_sec: 合成にかかった時間 (秒)。
        model_id: 実際に使ったモデル。起動時に申告したものと違うとき
            だけ入れる (Qwen はリクエストの内容で切り替えるため)。
    """

    sample_rate: int
    duration_sec: float
    elapsed_sec: float
    model_id: str | None = None

    def to_json(self) -> dict[str, object]:
        """封筒に入れて返せる辞書にする。"""
        return {
            "sample_rate": self.sample_rate,
            "duration_sec": self.duration_sec,
            "elapsed_sec": self.elapsed_sec,
            "model_id": self.model_id,
        }

    @classmethod
    def from_json(cls, data: dict) -> SynthesisResponse:
        """封筒から取り出した辞書を復元する。

        Args:
            data: 受け取った 1 行ぶんの辞書。

        Returns:
            SynthesisResponse: 復元した結果。

        Raises:
            ValueError: 必須の項目が無い、または値が不正なとき。
        """
        try:
            return cls(
                sample_rate=int(data["sample_rate"]),
                duration_sec=float(data["duration_sec"]),
                elapsed_sec=float(data["elapsed_sec"]),
                model_id=data.get("model_id"),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"Malformed response: {data}") from e
