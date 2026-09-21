"""TTS エンジンの抽象インターフェース。"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from types import TracebackType
from typing import Self

from .types import (
    Capability,
    EngineSpec,
    SynthesisRequest,
    SynthesisResult,
    UnsupportedLanguageError,
    UnsupportedParameterError,
)


class TTSEngine(ABC):
    """どのモデルでも同じ呼び出し方ができるようにする抽象。

    context manager として使う。``__exit__`` でバックエンドの資源（サブプロセス、
    将来的には HTTP セッション等）を確実に解放する。
    """

    def __init__(self, spec: EngineSpec) -> None:
        self.spec = spec

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def model_id(self) -> str:
        return self.spec.model_id

    def validate(self, request: SynthesisRequest) -> None:
        """エンジンが対応できないリクエストを、重いプロセスを起動する前に弾く。

        未対応を黙って無視すると「指定したのに効いていない」という最も気づきにくい
        不具合になるため、必ず例外にする。
        """
        spec = self.spec

        if request.language is not None and request.language not in spec.languages:
            raise UnsupportedLanguageError(
                f"エンジン '{spec.name}' は言語 '{request.language}' に対応していません。"
                f" 対応言語: {', '.join(spec.languages)}"
            )

        if request.reference_audio is not None:
            if not spec.supports(Capability.CLONE):
                raise UnsupportedParameterError(
                    f"エンジン '{spec.name}' は参照音声によるクローンに対応していません。"
                )
            if not request.reference_audio.is_file():
                raise FileNotFoundError(f"参照音声が見つかりません: {request.reference_audio}")

        if request.voice_design is not None and not spec.supports(Capability.VOICE_DESIGN):
            raise UnsupportedParameterError(
                f"エンジン '{spec.name}' は Voice Design（文章による声の設計）に"
                f"対応していません。参照音声によるクローン（--ref）を使ってください。"
            )

        if request.speed != 1.0 and not spec.supports(Capability.SPEED):
            raise UnsupportedParameterError(
                f"エンジン '{spec.name}' は speed 指定に対応していません"
                f" (speed={request.speed})。1.0 のままにしてください。"
            )

        if request.seed is not None and not spec.supports(Capability.SEED):
            raise UnsupportedParameterError(
                f"エンジン '{spec.name}' は seed 指定に対応していません。"
            )

    @abstractmethod
    def start(self) -> None:
        """モデルをロードし、合成を受け付けられる状態にする。"""

    @abstractmethod
    def close(self) -> None:
        """資源を解放する。多重呼び出しは安全であること。"""

    @abstractmethod
    def _synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """検証済みリクエストを実際に合成する。サブクラスが実装する。"""

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        self.validate(request)
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        return self._synthesize(request)

    def synthesize_many(self, requests: list[SynthesisRequest]) -> list[SynthesisResult]:
        """複数件をまとめて合成する。モデルはロードしたまま使い回される。"""
        return [self.synthesize(r) for r in requests]

    def __enter__(self) -> Self:
        # ここでは start() しない。未対応の言語やパラメータは validate() で弾くので、
        # 重いモデルのロード（10〜60 秒）を始める前にエラーにしたい。
        # 実際の起動は最初の synthesize() まで遅延する。
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def default_output_for(engine: str, text: str, outdir: Path) -> Path:
    """テキストから決定的なファイル名を作る（再レンダー時のキャッシュ用）。"""
    digest = hashlib.sha256(f"{engine}\n{text}".encode()).hexdigest()[:12]
    return outdir / f"{engine}-{digest}.wav"
