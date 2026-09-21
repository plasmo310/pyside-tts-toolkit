"""各サブコマンドの処理。

引数の定義と dispatch は `__main__.py` にあり、ここには「解析済みの引数を
受け取って仕事をする」関数だけを置く。どれも `core` の API を呼ぶだけで、
合成そのもののロジックは持たない。

進捗とエラーは標準エラーへ (`logger`)、結果そのもの (書き出したパスなど)
は標準出力へ出す。パイプで拾うときに混ざらないようにするため。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys

from ttstoolkit.core.interface import create_engine
from ttstoolkit.core.jobs import load_batch_items, run_batch, run_script
from ttstoolkit.core.paths import (
    BATCH_DIR,
    ROOT_DIR,
    SCRIPT_DIR,
    VOICES_DIR,
    resolve_input,
)
from ttstoolkit.core.script import load_script
from ttstoolkit.core.settings import (
    ROOT_LOGGER_NAME,
    SUBPROCESS_FLAGS,
    TTSToolkitError,
)
from ttstoolkit.core.types import (
    Capability,
    EngineSpec,
    SynthesisResult,
    default_output_path,
)
from ttstoolkit.engine._shared.protocol import SynthesisRequest
from ttstoolkit.tool_config import available_engines

logger = logging.getLogger(ROOT_LOGGER_NAME)

# `--cast` を省いたときに台本の隣から探すファイル名
_DEFAULT_CAST_NAME = "cast.toml"

# engines の表に並べる順番 (よく使うものから)
_CAPABILITY_ORDER = (
    Capability.CLONE,
    Capability.VOICE_DESIGN,
    Capability.SPEED,
    Capability.SEED,
    Capability.MULTILINGUAL,
)
_COLUMN_WIDTH = 14

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


# ---------------------------------------------------------------------
# 共通のヘルパ
# ---------------------------------------------------------------------


def resolve_existing(path: str, default_dir: str, missing_message: str) -> str:
    """入力パスを解決し、実在することを確かめる。

    Args:
        path: 利用者が指定したパス。
        default_dir: 見つからないときに最後に探す既定の置き場。
        missing_message: 見つからないときの文言。末尾にパスが付く。

    Returns:
        str: 実在が確認できたパス。

    Raises:
        TTSToolkitError: どこにも見つからないとき。
    """
    resolved = resolve_input(path, default_dir)
    if not os.path.isfile(resolved):
        raise TTSToolkitError(f"{missing_message}: {resolved}")
    return resolved


def report_result(result: SynthesisResult) -> None:
    """1 件の合成結果を標準出力へ出す。

    Args:
        result: 合成結果。
    """
    print(f"wrote {result.output_path}")
    print(f"  model    {result.model_id}")
    print(f"  audio    {result.sample_rate} Hz / {result.duration_sec:.2f}s")
    print(f"  took     {result.elapsed_sec:.2f}s")


def _print_progress(line: str) -> None:
    """まとめて合成するときの進捗を標準出力へ出す。"""
    print(line, flush=True)


# ---------------------------------------------------------------------
# synth
# ---------------------------------------------------------------------


def cmd_synth(args: argparse.Namespace) -> int:
    """テキストを 1 件だけ音声にする。

    Args:
        args: 解析済みの引数。

    Returns:
        int: 正常終了なら 0。
    """
    text = _read_text(args)
    reference = (
        resolve_existing(
            args.reference, VOICES_DIR, "Reference audio not found"
        )
        if args.reference
        else None
    )

    request = SynthesisRequest(
        text=text,
        output_path=_resolve_output(args, text),
        language=args.language,
        reference_audio=reference,
        reference_text=args.reference_text,
        voice_design=args.voice_design,
        seed=args.seed,
        speed=args.speed,
    )

    with create_engine(args.engine, verbose=args.verbose) as engine:
        result = engine.synthesize(request)

    report_result(result)
    return 0


def _read_text(args: argparse.Namespace) -> str:
    """読み上げるテキストを取り出す。

    Args:
        args: 解析済みの引数。

    Returns:
        str: 読み上げるテキスト。

    Raises:
        TTSToolkitError: テキストファイルが見つからないとき。
    """
    if args.text is not None:
        return args.text
    path = resolve_input(args.text_file)
    if not os.path.isfile(path):
        raise TTSToolkitError(f"Text file not found: {path}")
    with open(path, encoding="utf-8") as file:
        return file.read().strip()


def _resolve_output(args: argparse.Namespace, text: str) -> str:
    """書き出し先のパスを決める。

    `--output` が絶対パスならそのまま、相対パスなら `--output-dir` から
    たどる。省略されたときはテキストから決まる名前を使う。

    Args:
        args: 解析済みの引数。
        text: 読み上げるテキスト。

    Returns:
        str: 書き出す wav のパス。
    """
    if args.output is None:
        return default_output_path(args.engine, text, args.output_dir)
    if os.path.isabs(args.output):
        return args.output
    return os.path.join(args.output_dir, args.output)


# ---------------------------------------------------------------------
# batch
# ---------------------------------------------------------------------


def cmd_batch(args: argparse.Namespace) -> int:
    """JSON に並べたテキストをまとめて音声にする。

    Args:
        args: 解析済みの引数。

    Returns:
        int: 全件成功なら 0、1 件でも失敗があれば 1。
    """
    input_path = resolve_existing(
        args.input, BATCH_DIR, "Batch input not found"
    )
    items = load_batch_items(input_path)
    logger.info("%d items from %s", len(items), input_path)

    outcome = run_batch(
        engine_name=args.engine,
        items=items,
        output_dir=args.output_dir,
        keep_going=args.keep_going,
        verbose=args.verbose,
        on_progress=_print_progress,
    )

    logger.info(
        "%d/%d succeeded", len(outcome.written_paths), outcome.total_count
    )
    return 1 if outcome.failures else 0


# ---------------------------------------------------------------------
# script
# ---------------------------------------------------------------------


def cmd_script(args: argparse.Namespace) -> int:
    """キャラクター台本からまとめて音声にする。

    Args:
        args: 解析済みの引数。

    Returns:
        int: 全台詞成功なら 0、1 つでも失敗があれば 1。
    """
    script_path = resolve_existing(
        args.script, SCRIPT_DIR, "Script file not found"
    )
    script = load_script(_resolve_cast(args, script_path), script_path)

    logger.info(
        "%d lines / %d characters / engines: %s",
        len(script.lines),
        len(script.voices_used()),
        ", ".join(script.engines_used()),
    )

    outcome = run_script(
        script=script,
        output_dir=args.output_dir,
        gap_sec=args.gap,
        keep_going=args.keep_going,
        verbose=args.verbose,
        on_progress=_print_progress,
    )

    logger.info(
        "%d/%d lines synthesized",
        len(outcome.written_paths),
        outcome.total_count,
    )
    return 1 if outcome.failures else 0


def _resolve_cast(args: argparse.Namespace, script_path: str) -> str:
    """キャスト定義のパスを決める。

    Args:
        args: 解析済みの引数。
        script_path: 解決済みの台本のパス。

    Returns:
        str: キャスト定義のパス。

    Raises:
        TTSToolkitError: 見つからないとき。
    """
    if args.cast is None:
        directory = os.path.dirname(os.path.abspath(script_path))
        return resolve_existing(
            os.path.join(directory, _DEFAULT_CAST_NAME),
            SCRIPT_DIR,
            "Cast file not found",
        )
    return resolve_existing(args.cast, SCRIPT_DIR, "Cast file not found")


# ---------------------------------------------------------------------
# engines
# ---------------------------------------------------------------------


def cmd_engines(args: argparse.Namespace) -> int:
    """エンジンの一覧と、それぞれが何に対応しているかを表示する。

    Args:
        args: 解析済みの引数。

    Returns:
        int: 常に 0。
    """
    specs = available_engines()

    header = f"{'engine':<12} {'state':<11} {'lang':<8} " + "".join(
        f"{capability.name.lower():<{_COLUMN_WIDTH}}"
        for capability in _CAPABILITY_ORDER
    )
    print(header)
    print("-" * len(header))
    for name, spec in specs.items():
        print(_format_engine_row(name, spec))

    print()
    for name, spec in specs.items():
        print(f"{name}: {spec.description}")
        print(f"  model  {spec.model_id}")
        print(f"  python {spec.python}")
        if not spec.installed:
            print(f"  -> not set up; see docs/setup/{spec.setup_doc}")
    return 0


def _format_engine_row(name: str, spec: EngineSpec) -> str:
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


# ---------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    """環境の健全性をまとめて調べる。

    合成がうまくいかないときに最初に叩くコマンド。エンジンの仮想環境は
    互いに独立しているので、それぞれの python を子プロセスとして起動して
    調べる。

    Args:
        args: 解析済みの引数。

    Returns:
        int: すべて構築済みなら 0、未構築があれば 1。
    """
    print("== Toolkit ==")
    print(f"python  {sys.version.split()[0]}")
    print(f"        {sys.executable}")
    print(f"root    {ROOT_DIR}")

    print("\n== GPU ==")
    _show_gpu()

    print("\n== Engines ==")
    is_ready = True
    for name, spec in available_engines().items():
        print(f"\n[{name}] {spec.model_id}")
        if not spec.installed:
            print(f"  not set up; see docs/setup/{spec.setup_doc}")
            is_ready = False
            continue
        print(f"  {_probe_engine(spec)}")
    return 0 if is_ready else 1


def _show_gpu() -> None:
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
            creationflags=SUBPROCESS_FLAGS,
        )
    except (OSError, subprocess.TimeoutExpired):
        print("nvidia-smi not found (synthesis will run on CPU)")
        return
    if completed.returncode != 0:
        print("nvidia-smi failed")
        return
    print(completed.stdout.strip())


def _probe_engine(spec: EngineSpec) -> str:
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
            creationflags=SUBPROCESS_FLAGS,
        )
    except subprocess.TimeoutExpired:
        return "importing torch timed out"

    if completed.returncode != 0:
        tail = (completed.stderr or "").strip().splitlines()
        detail = tail[-1] if tail else "(no detail)"
        return f"could not import torch: {detail}"

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
