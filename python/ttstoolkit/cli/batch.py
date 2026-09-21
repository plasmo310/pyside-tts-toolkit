"""サンプル2: JSON に並べたテキストをまとめて音声にする。

使い方:
    python -m ttstoolkit.cli.batch -e qwen input/batch/sample.ja.json
    python -m ttstoolkit.cli.batch -e irodori sample.ja.json -o output/ja

入力 JSON はオブジェクトの配列で、`text` だけが必須::

    [
      {"id": "line-001", "text": "こんにちは。", "language": "ja"},
      {"id": "line-002", "text": "今日はいい天気ですね。"}
    ]

1 つの runner を常駐させたまま全件を流すので、2 件目以降はモデルの
ロード時間を払わない。
"""

from __future__ import annotations

import argparse

from ttstoolkit.cli.common import (
    add_common_args,
    add_engine_arg,
    add_output_dir_arg,
    logger,
    resolve_existing,
    run,
)
from ttstoolkit.engine.jobs import load_batch_items, run_batch
from ttstoolkit.engine.paths import BATCH_DIR


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析する。

    Returns:
        argparse.Namespace: 解析済みの引数。

    Raises:
        SystemExit: 引数が不正なとき、または -h/--help のとき。
    """
    parser = argparse.ArgumentParser(
        prog="python -m ttstoolkit.cli.batch",
        description="Synthesize every line in a JSON file",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input",
        help="Input JSON. Relative paths are searched from the current "
        "directory, repository root, then input/batch",
    )
    add_engine_arg(parser)
    add_output_dir_arg(parser)
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue with the remaining lines after a failure",
    )
    add_common_args(parser)
    return parser.parse_args()


def main() -> int:
    """バッチ入力を読み、まとめて合成して書き出す。

    Returns:
        int: 全件成功なら 0、1 件でも失敗があれば 1。
    """
    args = parse_args()
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
        on_progress=lambda line: print(line, flush=True),
    )

    logger.info(
        "%d/%d succeeded", len(outcome.written_paths), outcome.total_count
    )
    return 1 if outcome.failures else 0


if __name__ == "__main__":
    raise SystemExit(run(main))
