"""エンジンの一覧と、それぞれが何に対応しているかを表示する。

使い方:
    python -m ttstoolkit.cli.engines

対応していないパラメータを渡すとエンジンは黙って無視せずエラーにする
ので、何が使えるかをここで先に確かめられる。
"""

from __future__ import annotations

import argparse

from ttstoolkit.cli.common import run
from ttstoolkit.engine.registry import available_engines
from ttstoolkit.engine.types import Capability, EngineSpec

# 表に並べる順番 (よく使うものから)
_CAPABILITY_ORDER = (
    Capability.CLONE,
    Capability.VOICE_DESIGN,
    Capability.SPEED,
    Capability.SEED,
    Capability.MULTILINGUAL,
)

_COLUMN_WIDTH = 14


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析する。

    Returns:
        argparse.Namespace: 解析済みの引数。

    Raises:
        SystemExit: 引数が不正なとき、または -h/--help のとき。
    """
    parser = argparse.ArgumentParser(
        prog="python -m ttstoolkit.cli.engines",
        description="List the engines and what they support",
    )
    return parser.parse_args()


def format_row(name: str, spec: EngineSpec) -> str:
    """一覧の 1 行を作る。

    Args:
        name: エンジン名。
        spec: そのエンジンの定義。

    Returns:
        str: 表の 1 行。
    """
    state = "ready" if spec.installed else "not set up"
    cells = "".join(
        f"{('yes' if spec.supports(capability) else '-'):<{_COLUMN_WIDTH}}"
        for capability in _CAPABILITY_ORDER
    )
    languages = ",".join(spec.languages)
    return f"{name:<12} {state:<11} {languages:<8} {cells}"


def main() -> int:
    """エンジンの一覧を表示する。

    Returns:
        int: 常に 0。
    """
    parse_args()
    specs = available_engines()

    header = f"{'engine':<12} {'state':<11} {'lang':<8} " + "".join(
        f"{capability.name.lower():<{_COLUMN_WIDTH}}"
        for capability in _CAPABILITY_ORDER
    )
    print(header)
    print("-" * len(header))
    for name, spec in specs.items():
        print(format_row(name, spec))

    print()
    for name, spec in specs.items():
        print(f"{name}: {spec.description}")
        print(f"  model  {spec.model_id}")
        print(f"  python {spec.python}")
        if not spec.installed:
            print(f"  -> not set up; see docs/setup/{spec.setup_doc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(main))
