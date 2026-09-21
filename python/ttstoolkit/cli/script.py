"""サンプル3: キャラクター台本からまとめて音声にする。

使い方:
    python -m ttstoolkit.cli.script ep01.ja.txt -c cast.toml -o output/ep01

台本の書き方は `ttstoolkit.engine.script` の docstring を参照。声の
定義 (cast.toml) は一度書けば使い回せるので、毎回書くのは台詞だけで
済む。

話者ごとにエンジンが違ってもよい。同じエンジンの台詞はまとめて処理し、
manifest では台本順に並べ直して `start_sec` (先頭からの秒数) を付ける。
"""

from __future__ import annotations

import argparse
import os

from ttstoolkit.cli.common import (
    add_common_args,
    add_output_dir_arg,
    logger,
    resolve_existing,
    run,
)
from ttstoolkit.engine.jobs import run_script
from ttstoolkit.engine.paths import SCRIPT_DIR
from ttstoolkit.engine.script import load_script

# --cast を省略したときに台本の隣から探すファイル名
_DEFAULT_CAST_NAME = "cast.toml"


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析する。

    Returns:
        argparse.Namespace: 解析済みの引数。

    Raises:
        SystemExit: 引数が不正なとき、または -h/--help のとき。
    """
    parser = argparse.ArgumentParser(
        prog="python -m ttstoolkit.cli.script",
        description="Synthesize a character script",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "script",
        help="Script text. Relative paths are searched from the current "
        "directory, repository root, then input/script",
    )
    parser.add_argument(
        "-c",
        "--cast",
        default=None,
        metavar="TOML",
        help=f"Cast file. Defaults to {_DEFAULT_CAST_NAME} next to the script",
    )
    add_output_dir_arg(parser)
    parser.add_argument(
        "--gap",
        type=float,
        default=0.3,
        help="Silence between lines used to compute start_sec (seconds)",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue with the remaining lines after a failure",
    )
    add_common_args(parser)
    return parser.parse_args()


def resolve_cast(args: argparse.Namespace, script_path: str) -> str:
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


def main() -> int:
    """台本を読み、まとめて合成して書き出す。

    Returns:
        int: 全台詞成功なら 0、1 つでも失敗があれば 1。
    """
    args = parse_args()
    script_path = resolve_existing(
        args.script, SCRIPT_DIR, "Script file not found"
    )
    script = load_script(resolve_cast(args, script_path), script_path)

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
        on_progress=lambda line: print(line, flush=True),
    )

    logger.info(
        "%d/%d lines synthesized",
        len(outcome.written_paths),
        outcome.total_count,
    )
    return 1 if outcome.failures else 0


if __name__ == "__main__":
    raise SystemExit(run(main))
