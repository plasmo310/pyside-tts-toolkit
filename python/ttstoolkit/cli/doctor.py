"""環境の健全性をまとめて調べる。

使い方:
    python -m ttstoolkit.cli.doctor

合成が動かないときに最初に叩くコマンド。共通層の Python、GPU、そして
エンジンごとの仮想環境の中の torch と CUDA を順に確かめる。エンジンの
仮想環境は互いに独立しているので、それぞれの python を子プロセスとして
起動して調べる。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from ttstoolkit.cli.common import run
from ttstoolkit.engine.paths import ROOT_DIR
from ttstoolkit.engine.registry import available_engines
from ttstoolkit.engine.types import EngineSpec

# エンジンの仮想環境の中で走らせて torch の状態を持ち帰るコード
_PROBE_CODE = (
    "import json,torch;"
    "print(json.dumps({'torch':torch.__version__,"
    "'cuda':torch.cuda.is_available(),"
    "'device':(torch.cuda.get_device_name(0)"
    " if torch.cuda.is_available() else None),"
    "'arch':(list(torch.cuda.get_arch_list())"
    " if torch.cuda.is_available() else [])}))"
)

# Blackwell (RTX 50 系) は sm_120。対応アーキに含まれるかまで見る
_BLACKWELL_ARCH_SUFFIX = "_120"


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析する。

    Returns:
        argparse.Namespace: 解析済みの引数。

    Raises:
        SystemExit: 引数が不正なとき、または -h/--help のとき。
    """
    parser = argparse.ArgumentParser(
        prog="python -m ttstoolkit.cli.doctor",
        description="Check that the environment is ready to synthesize",
    )
    return parser.parse_args()


def probe_engine(spec: EngineSpec) -> str:
    """エンジンの仮想環境の中で torch と CUDA の状態を調べる。

    Args:
        spec: 調べるエンジンの定義。

    Returns:
        str: 1 行にまとめた状態。
    """
    try:
        completed = subprocess.run(
            [spec.python, "-c", _PROBE_CODE],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "importing torch timed out"

    if completed.returncode != 0:
        tail = (completed.stderr or "").strip().splitlines()
        return f"could not import torch: {tail[-1] if tail else '(no detail)'}"

    info = json.loads(completed.stdout.strip().splitlines()[-1])
    if not info["cuda"]:
        return f"torch {info['torch']} / CUDA unavailable (CPU only)"

    note = ""
    if info["arch"] and not any(
        arch.endswith(_BLACKWELL_ARCH_SUFFIX) for arch in info["arch"]
    ):
        note = (
            f"  ! sm_120 is missing from arch_list: {','.join(info['arch'])}"
        )
    return f"torch {info['torch']} / CUDA ok / {info['device']}{note}"


def show_gpu() -> None:
    """nvidia-smi で GPU の状態を表示する。"""
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,driver_version",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        print("nvidia-smi not found (synthesis will run on CPU)")
        return
    if completed.returncode != 0:
        print("nvidia-smi failed")
        return
    print(completed.stdout.strip())


def main() -> int:
    """環境を順に調べて表示する。

    Returns:
        int: すべて構築済みなら 0、未構築があれば 1。
    """
    parse_args()

    print("== Toolkit ==")
    print(f"python  {sys.version.split()[0]}")
    print(f"        {sys.executable}")
    print(f"root    {ROOT_DIR}")

    print("\n== GPU ==")
    show_gpu()

    print("\n== Engines ==")
    is_ready = True
    for name, spec in available_engines().items():
        print(f"\n[{name}] {spec.model_id}")
        if not spec.installed:
            print(f"  not set up; see docs/setup/{spec.setup_doc}")
            is_ready = False
            continue
        print(f"  {probe_engine(spec)}")
    return 0 if is_ready else 1


if __name__ == "__main__":
    raise SystemExit(run(main))
