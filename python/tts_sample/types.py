"""共通の入出力型とエラー。

このモジュールは torch を含むモデル依存を一切持たない。GUI や Remotion 連携から
そのまま import できることが設計上の前提になっている。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Flag, auto
from pathlib import Path


class Capability(Flag):
    """エンジンが対応している機能。未対応パラメータは暗黙に無視せず明示エラーにする。"""

    NONE = 0
    CLONE = auto()  # 参照音声によるゼロショットクローン
    SPEED = auto()  # 話速指定
    SEED = auto()  # 乱数シード固定
    MULTILINGUAL = auto()  # 日本語以外も生成できる
    VOICE_DESIGN = auto()  # 文章の指示から声そのものを設計する


class TTSError(Exception):
    """このパッケージが送出する例外の基底。"""


class EngineNotFoundError(TTSError):
    """engines.toml に定義されていないエンジン名が指定された。"""


class EngineNotInstalledError(TTSError):
    """エンジンの venv がまだ構築されていない。"""


class UnsupportedParameterError(TTSError):
    """エンジンが対応していないパラメータが既定値以外で渡された。"""


class UnsupportedLanguageError(TTSError):
    """エンジンが対応していない言語が指定された。"""


class EngineProcessError(TTSError):
    """runner プロセスの起動・通信・合成が失敗した。"""


@dataclass(frozen=True)
class SynthesisRequest:
    """1 件の合成リクエスト。全エンジン共通。

    ``reference_text`` は Qwen3-TTS の ``generate_base`` が参照音声の書き起こしを
    要求するためにある。Chatterbox と Irodori では使われない。未指定の場合 Qwen は
    話者埋め込みのみを使うモード（x_vector_only_mode）にフォールバックする。
    """

    text: str
    output_path: Path
    language: str | None = None  # "ja" | "en"。None はエンジン既定/自動判定。
    reference_audio: Path | None = None
    reference_text: str | None = None
    voice_design: str | None = None
    seed: int | None = None
    speed: float = 1.0

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("text が空です。")
        if self.speed <= 0:
            raise ValueError(f"speed は正の数である必要があります: {self.speed}")

    def to_payload(self) -> dict:
        """runner へ送る JSON 表現。Path は文字列化する。"""
        return {
            "text": self.text,
            "output_path": str(self.output_path),
            "language": self.language,
            "reference_audio": str(self.reference_audio) if self.reference_audio else None,
            "reference_text": self.reference_text,
            "voice_design": self.voice_design,
            "seed": self.seed,
            "speed": self.speed,
        }


@dataclass(frozen=True)
class SynthesisResult:
    """1 件の合成結果。"""

    output_path: Path
    sample_rate: int
    duration_sec: float
    engine: str
    model_id: str
    elapsed_sec: float

    def to_dict(self) -> dict:
        return {
            "output_path": str(self.output_path),
            "sample_rate": self.sample_rate,
            "duration_sec": round(self.duration_sec, 3),
            "engine": self.engine,
            "model_id": self.model_id,
            "elapsed_sec": round(self.elapsed_sec, 3),
        }


@dataclass(frozen=True)
class BatchItem:
    """バッチ入力 JSON の 1 要素。"""

    id: str
    text: str
    language: str | None = None
    reference_audio: Path | None = None
    reference_text: str | None = None
    voice_design: str | None = None
    seed: int | None = None
    speed: float = 1.0

    @classmethod
    def from_dict(cls, data: dict, index: int, base_dir: Path) -> BatchItem:
        if "text" not in data:
            raise ValueError(f"バッチ入力の {index} 件目に text がありません。")
        ref = data.get("reference_audio")
        return cls(
            id=str(data.get("id", f"item-{index:04d}")),
            text=str(data["text"]),
            language=data.get("language"),
            reference_audio=(base_dir / ref).resolve() if ref else None,
            reference_text=data.get("reference_text"),
            voice_design=data.get("voice_design"),
            seed=data.get("seed"),
            speed=float(data.get("speed", 1.0)),
        )

    def to_request(self, output_path: Path) -> SynthesisRequest:
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
    """engines.toml の 1 エントリ。"""

    name: str
    description: str
    capabilities: Capability
    languages: tuple[str, ...]
    model_id: str
    python: Path  # エンジン venv の python 実行ファイル
    runner: Path  # runner.py の絶対パス
    cwd: Path  # runner を起動する作業ディレクトリ
    setup_doc: str  # docs/setup 配下の該当ファイル
    options: dict = field(default_factory=dict)  # runner へそのまま渡すエンジン固有設定
    env: dict = field(default_factory=dict)  # runner プロセスへ追加する環境変数

    def supports(self, cap: Capability) -> bool:
        return bool(self.capabilities & cap)

    @property
    def installed(self) -> bool:
        return self.python.is_file() and self.runner.is_file()
