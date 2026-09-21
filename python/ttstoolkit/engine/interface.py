"""どのモデルでも同じ呼び方ができるようにする共通インターフェース。

3 つのモデルは依存ライブラリのピンが互いに排他的で、1 つの仮想環境には
同居できない。そのため実装は必ずプロセス境界をまたぐが、呼ぶ側は
その事情を知らなくてよい ── それがこの抽象の目的。

    with create_engine("irodori") as engine:
        result = engine.synthesize(request)

`__enter__` では `start()` を呼ばない。未対応の言語やパラメータは
`validate()` が弾くので、重いモデルのロード (10〜60 秒) を始める前に
エラーにしたいため。実際の起動は最初の `synthesize()` まで遅延する。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from ttstoolkit.engine.types import (
    Capability,
    EngineSpec,
    SynthesisRequest,
    SynthesisResult,
    UnsupportedLanguageError,
    UnsupportedParameterError,
)


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
