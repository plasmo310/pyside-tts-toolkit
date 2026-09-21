"""エンジン名から `TTSEngine` を作る。

将来 HTTP バックエンド (Irodori-TTS-Server のような OpenAI 互換サーバ)
を足す場合は、ここに分岐を 1 つ増やすだけで済む。呼び出し側と
`TTSEngine` のインターフェースは変わらない。
"""

from __future__ import annotations

from ttstoolkit.engine.interface import TTSEngine
from ttstoolkit.engine.subprocess_engine import SubprocessEngine
from ttstoolkit.engine.types import EngineNotFoundError, EngineSpec
from ttstoolkit.tool_config import ENGINE_DEFINITIONS


def engine_names() -> list[str]:
    """使えるエンジン名を定義順で返す。"""
    return list(ENGINE_DEFINITIONS)


def available_engines() -> dict[str, EngineSpec]:
    """エンジン名 -> 定義の辞書を返す。"""
    return dict(ENGINE_DEFINITIONS)


def get_spec(name: str) -> EngineSpec:
    """エンジン名から定義を返す。

    Args:
        name: エンジン名。

    Returns:
        EngineSpec: そのエンジンの定義。

    Raises:
        EngineNotFoundError: 定義されていない名前のとき。
    """
    spec = ENGINE_DEFINITIONS.get(name)
    if spec is None:
        raise EngineNotFoundError(
            f"Unknown engine '{name}' (available: {', '.join(engine_names())})"
        )
    return spec


def create_engine(name: str, verbose: bool = False) -> TTSEngine:
    """エンジンを生成する。呼び出し側は with 文で使うこと。

    Args:
        name: エンジン名。
        verbose: runner の stderr をそのままログへ流すか。

    Returns:
        TTSEngine: 生成したエンジン。

    Raises:
        EngineNotFoundError: 定義されていない名前のとき。
    """
    return SubprocessEngine(get_spec(name), verbose=verbose)
