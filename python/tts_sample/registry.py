"""エンジン名から TTSEngine を作る。

将来 HTTP バックエンド（Irodori-TTS-Server のような OpenAI 互換サーバ）を足す場合は
ここに分岐を 1 つ増やすだけで済む。呼び出し側と共通インターフェースは変わらない。
"""

from __future__ import annotations

from .config import load_specs
from .engine import TTSEngine
from .subprocess_engine import SubprocessEngine
from .types import EngineNotFoundError, EngineSpec


def available_engines() -> dict:
    """エンジン名 -> EngineSpec。"""
    return load_specs()


def engine_names() -> list:
    return sorted(load_specs())


def get_spec(name: str) -> EngineSpec:
    specs = load_specs()
    if name not in specs:
        raise EngineNotFoundError(
            f"未知のエンジン '{name}'。使えるのは: {', '.join(sorted(specs))}"
        )
    return specs[name]


def create_engine(name: str, *, verbose: bool = False) -> TTSEngine:
    """エンジンを生成する。呼び出し側は with 文で使うこと。"""
    return SubprocessEngine(get_spec(name), verbose=verbose)
