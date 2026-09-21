"""複数の TTS モデルを共通インターフェースで扱うサンプル。

使い方:

    from tts_sample import create_engine, SynthesisRequest
    from pathlib import Path

    with create_engine("chatterbox") as engine:
        result = engine.synthesize(
            SynthesisRequest(text="こんにちは。", output_path=Path("out.wav"), language="ja")
        )
    print(result.duration_sec)
"""

from .engine import TTSEngine, default_output_for
from .registry import available_engines, create_engine, engine_names, get_spec
from .types import (
    BatchItem,
    Capability,
    EngineNotFoundError,
    EngineNotInstalledError,
    EngineProcessError,
    EngineSpec,
    SynthesisRequest,
    SynthesisResult,
    TTSError,
    UnsupportedLanguageError,
    UnsupportedParameterError,
)

__all__ = [
    "BatchItem",
    "Capability",
    "EngineNotFoundError",
    "EngineNotInstalledError",
    "EngineProcessError",
    "EngineSpec",
    "SynthesisRequest",
    "SynthesisResult",
    "TTSEngine",
    "TTSError",
    "UnsupportedLanguageError",
    "UnsupportedParameterError",
    "available_engines",
    "create_engine",
    "default_output_for",
    "engine_names",
    "get_spec",
]

__version__ = "0.1.0"
