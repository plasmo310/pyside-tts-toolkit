"""engines.toml の読み込みと EngineSpec への変換。"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

from .subprocess_engine import resolve_venv_python
from .types import Capability, EngineSpec, TTSError

CONFIG_FILENAME = "engines.toml"


def project_root() -> Path:
    """python/ ディレクトリ（engines.toml が置かれている場所）を返す。

    tts_sample/config.py -> tts_sample -> python
    """
    return Path(__file__).resolve().parents[1]


def repo_root() -> Path:
    """リポジトリのルートを返す。

    engines.toml のパスはここを基準に書く。仮想環境が .venvs/ に、
    runner が python/engines/ にと別の枝へ散るため、両方を素直に
    書ける位置をひとつの基準にしている。
    """
    return project_root().parent


def config_path() -> Path:
    return project_root() / CONFIG_FILENAME


def _parse_capabilities(names: list) -> Capability:
    cap = Capability.NONE
    for name in names:
        key = str(name).strip().upper()
        try:
            cap |= Capability[key]
        except KeyError as exc:
            valid = ", ".join(c.name for c in Capability if c.name != "NONE")
            raise TTSError(
                f"{CONFIG_FILENAME}: 未知の capability '{name}'。使えるのは: {valid}"
            ) from exc
    return cap


def _require(table: dict, key: str, engine: str) -> object:
    if key not in table:
        raise TTSError(f"{CONFIG_FILENAME}: エンジン '{engine}' に '{key}' がありません。")
    return table[key]


@lru_cache(maxsize=1)
def load_specs() -> dict:
    """engines.toml を読み、エンジン名 -> EngineSpec の辞書を返す。"""
    path = config_path()
    if not path.is_file():
        raise TTSError(f"設定ファイルが見つかりません: {path}")

    with path.open("rb") as fh:
        raw = tomllib.load(fh)

    root = repo_root()
    specs: dict = {}
    for name, table in raw.items():
        if not isinstance(table, dict):
            continue
        venv_dir = root / str(_require(table, "venv", name))
        specs[name] = EngineSpec(
            name=name,
            description=str(table.get("description", "")),
            capabilities=_parse_capabilities(table.get("capabilities", [])),
            languages=tuple(str(x) for x in _require(table, "languages", name)),
            model_id=str(_require(table, "model_id", name)),
            python=resolve_venv_python(venv_dir),
            runner=root / str(_require(table, "runner", name)),
            cwd=root / str(_require(table, "cwd", name)),
            setup_doc=str(table.get("setup_doc", "README.md")),
            options=dict(table.get("options", {})),
            env=dict(table.get("env", {})),
        )

    if not specs:
        raise TTSError(f"{path} にエンジンが 1 つも定義されていません。")
    return specs
