"""エンジンとやり取りするデータクラスと、エンジン固有のエラー。

このモジュールは torch を含むモデル依存を一切持たない。GUI からも CLI
からも、外部ツール (Remotion など) との連携コードからもそのまま import
できることが設計上の前提になっている。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from enum import Flag, auto

from ttstoolkit.engine.settings import TTSToolkitError


class Capability(Flag):
    """エンジンが対応している機能。

    未対応のパラメータを黙って無視すると「指定したのに効いていない」と
    いう最も気づきにくい不具合になるため、対応状況をここで宣言して
    `TTSEngine.validate()` が起動前に弾けるようにしている。
    """

    NONE = 0
    CLONE = auto()  # 参照音声によるゼロショットクローン
    SPEED = auto()  # 話速指定
    SEED = auto()  # 乱数シード固定
    MULTILINGUAL = auto()  # 日本語以外も生成できる
    VOICE_DESIGN = auto()  # 文章の指示から声そのものを設計する


class EngineNotFoundError(TTSToolkitError):
    """定義されていないエンジン名が指定された。"""


class EngineNotInstalledError(TTSToolkitError):
    """エンジンの仮想環境がまだ構築されていない。"""


class UnsupportedParameterError(TTSToolkitError):
    """エンジンが対応していないパラメータが既定値以外で渡された。"""


class UnsupportedLanguageError(TTSToolkitError):
    """エンジンが対応していない言語が指定された。"""


class EngineProcessError(TTSToolkitError):
    """runner プロセスの起動・通信・合成が失敗した。"""


@dataclass(frozen=True)
class SynthesisRequest:
    """1 件の合成リクエスト。全エンジン共通。

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
    """

    text: str
    output_path: str
    language: str | None = None
    reference_audio: str | None = None
    reference_text: str | None = None
    voice_design: str | None = None
    seed: int | None = None
    speed: float = 1.0

    def __post_init__(self) -> None:
        """入力を検査し、パスを絶対パスに直す。

        パスを絶対にするのは runner が別のカレントディレクトリで動く
        ため。相対パスのまま渡すと、書き出し先が runner 側の作業
        ディレクトリ基準になって行方不明になる (Irodori は clone の中で
        動かしている)。

        Raises:
            ValueError: テキストが空、または speed が 0 以下のとき。
        """
        if not self.text.strip():
            raise ValueError("Text is empty")
        if self.speed <= 0:
            raise ValueError(f"Speed must be positive: {self.speed}")

        object.__setattr__(
            self, "output_path", os.path.abspath(self.output_path)
        )
        if self.reference_audio:
            object.__setattr__(
                self,
                "reference_audio",
                os.path.abspath(self.reference_audio),
            )

    def to_payload(self) -> dict[str, object]:
        """runner へ送る JSON 表現を返す。"""
        return {
            "text": self.text,
            "output_path": self.output_path,
            "language": self.language,
            "reference_audio": self.reference_audio,
            "reference_text": self.reference_text,
            "voice_design": self.voice_design,
            "seed": self.seed,
            "speed": self.speed,
        }


@dataclass(frozen=True)
class SynthesisResult:
    """1 件の合成結果。

    Attributes:
        output_path: 書き出した wav のパス。
        sample_rate: サンプリングレート (Hz)。
        duration_sec: 音声の長さ (秒)。
        engine: 使ったエンジン名。
        model_id: 実際に使ったモデルの識別子。
        elapsed_sec: 合成にかかった時間 (秒)。
    """

    output_path: str
    sample_rate: int
    duration_sec: float
    engine: str
    model_id: str
    elapsed_sec: float

    def to_dict(self) -> dict[str, object]:
        """manifest に書き出すための辞書を返す。"""
        return {
            "output_path": self.output_path,
            "sample_rate": self.sample_rate,
            "duration_sec": round(self.duration_sec, 3),
            "engine": self.engine,
            "model_id": self.model_id,
            "elapsed_sec": round(self.elapsed_sec, 3),
        }


@dataclass(frozen=True)
class BatchItem:
    """バッチ入力 JSON の 1 要素。

    Attributes:
        id: 出力ファイル名に使う識別子。
        text: 読み上げるテキスト。
        language: 言語コード。
        reference_audio: 参照音声のパス。
        reference_text: 参照音声の書き起こし。
        voice_design: 文章による声の指定。
        seed: 乱数シード。
        speed: 話速。
    """

    id: str
    text: str
    language: str | None = None
    reference_audio: str | None = None
    reference_text: str | None = None
    voice_design: str | None = None
    seed: int | None = None
    speed: float = 1.0

    @classmethod
    def from_dict(cls, data: dict, index: int, base_dir: str) -> BatchItem:
        """JSON の 1 要素から作る。

        Args:
            data: JSON の 1 要素。
            index: 配列中の位置。エラーメッセージと既定 id に使う。
            base_dir: 参照音声の相対パスを解決する基準。

        Returns:
            BatchItem: 変換した 1 要素。

        Raises:
            ValueError: text が無いとき。
        """
        if "text" not in data:
            raise ValueError(f"Batch item {index} has no text")
        ref = data.get("reference_audio")
        return cls(
            id=str(data.get("id", f"item-{index:04d}")),
            text=str(data["text"]),
            language=data.get("language"),
            reference_audio=(
                os.path.abspath(os.path.join(base_dir, ref)) if ref else None
            ),
            reference_text=data.get("reference_text"),
            voice_design=data.get("voice_design"),
            seed=data.get("seed"),
            speed=float(data.get("speed", 1.0)),
        )

    def to_request(self, output_path: str) -> SynthesisRequest:
        """書き出し先を決めて合成リクエストにする。

        Args:
            output_path: 書き出す wav のパス。

        Returns:
            SynthesisRequest: 合成リクエスト。
        """
        return SynthesisRequest(
            text=self.text,
            output_path=output_path,
            language=self.language,
            reference_audio=self.reference_audio,
            reference_text=self.reference_text,
            voice_design=self.voice_design,
            seed=self.seed,
            speed=self.speed,
        )


@dataclass(frozen=True)
class EngineSpec:
    """1 つのエンジンの定義。実体は `tool_config.ENGINE_DEFINITIONS`。

    Attributes:
        name: エンジン名 (`qwen` など)。
        description: 一覧に出す説明。
        capabilities: 対応している機能。
        languages: 対応している言語コード。
        model_id: 既定で使うモデルの識別子。
        python: このエンジンの仮想環境の python 実行ファイル。
        runner: runner モジュール名 (`-m` に渡す)。
        cwd: runner を起動する作業ディレクトリ。
        setup_doc: `docs/setup/` 配下の該当ファイル名。
        options: runner へそのまま渡すエンジン固有の設定。
        python_path: runner の検索パスに足すディレクトリ。
    """

    name: str
    description: str
    capabilities: Capability
    languages: tuple[str, ...]
    model_id: str
    python: str
    runner: str
    cwd: str
    setup_doc: str
    options: dict = field(default_factory=dict)
    python_path: tuple[str, ...] = ()

    def supports(self, capability: Capability) -> bool:
        """機能に対応しているかを返す。

        Args:
            capability: 調べる機能。

        Returns:
            bool: 対応していれば True。
        """
        return bool(self.capabilities & capability)

    @property
    def installed(self) -> bool:
        """仮想環境が構築済みかを返す。"""
        return os.path.isfile(self.python)


def default_output_path(engine: str, text: str, output_dir: str) -> str:
    """テキストから決まるファイル名を作る (再生成時の取り違え防止)。

    Args:
        engine: エンジン名。
        text: 読み上げるテキスト。
        output_dir: 書き出し先ディレクトリ。

    Returns:
        str: 書き出す wav のパス。
    """
    digest = hashlib.sha256(f"{engine}\n{text}".encode()).hexdigest()[:12]
    return os.path.join(output_dir, f"{engine}-{digest}.wav")
