"""サンプル1: テキストを 1 件だけ音声にする。

使い方:
    python -m ttstoolkit.cli.synth -e irodori -t "こんにちは。"
    python -m ttstoolkit.cli.synth -e qwen -t "Hello." -l en -O hello.wav
    python -m ttstoolkit.cli.synth -e qwen -f line.txt -r master.wav
"""

from __future__ import annotations

import argparse
import os

from ttstoolkit.cli.common import (
    add_common_args,
    add_engine_arg,
    add_output_dir_arg,
    add_voice_args,
    report_result,
    resolve_existing,
    run,
)
from ttstoolkit.engine.paths import VOICES_DIR, resolve_input
from ttstoolkit.engine.registry import create_engine
from ttstoolkit.engine.settings import TTSToolkitError
from ttstoolkit.engine.types import SynthesisRequest, default_output_path


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析する。

    Returns:
        argparse.Namespace: 解析済みの引数。

    Raises:
        SystemExit: 引数が不正なとき、または -h/--help のとき。
    """
    parser = argparse.ArgumentParser(
        prog="python -m ttstoolkit.cli.synth",
        description="Synthesize one line of text",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_engine_arg(parser)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-t", "--text", help="Text to speak")
    source.add_argument(
        "-f", "--text-file", help="Read the text from a UTF-8 file"
    )
    parser.add_argument(
        "-O",
        "--output",
        default=None,
        metavar="WAV",
        help="Output file. Derived from the text when omitted",
    )
    add_output_dir_arg(parser)
    add_voice_args(parser)
    add_common_args(parser)
    return parser.parse_args()


def read_text(args: argparse.Namespace) -> str:
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


def resolve_output(args: argparse.Namespace, text: str) -> str:
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


def main() -> int:
    """1 件を合成して書き出す。

    Returns:
        int: 正常終了なら 0。
    """
    args = parse_args()
    text = read_text(args)
    reference = (
        resolve_existing(
            args.reference, VOICES_DIR, "Reference audio not found"
        )
        if args.reference
        else None
    )

    request = SynthesisRequest(
        text=text,
        output_path=resolve_output(args, text),
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


if __name__ == "__main__":
    raise SystemExit(run(main))
