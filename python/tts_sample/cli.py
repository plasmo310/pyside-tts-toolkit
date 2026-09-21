"""コマンドラインインターフェース。

    python -m tts_sample synth   --engine <name> --text "..." --out out.wav
    python -m tts_sample batch   --engine <name> --input items.json --outdir outputs/
    python -m tts_sample script  --cast cast.toml --script ep01.ja.txt --outdir outputs/ep01
    python -m tts_sample engines     エンジン一覧とケイパビリティ
    python -m tts_sample doctor      環境の健全性チェック
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import time
from pathlib import Path

from .config import config_path, project_root
from .registry import available_engines, create_engine, engine_names, get_spec
from .script import load_script
from .types import BatchItem, Capability, SynthesisRequest, TTSError

PREVIEW_CHARS = 24  # 進捗表示で台詞を切り詰める幅

_CAP_ORDER = (
    Capability.CLONE,
    Capability.VOICE_DESIGN,
    Capability.SPEED,
    Capability.SEED,
    Capability.MULTILINGUAL,
)


def _read_text(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text
    path = Path(args.text_file)
    if not path.is_file():
        raise TTSError(f"テキストファイルが見つかりません: {path}")
    return path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------- synth


def cmd_synth(args: argparse.Namespace) -> int:
    text = _read_text(args)
    request = SynthesisRequest(
        text=text,
        output_path=Path(args.out).resolve(),
        language=args.lang,
        reference_audio=Path(args.ref).resolve() if args.ref else None,
        reference_text=args.ref_text,
        voice_design=args.voice_design,
        seed=args.seed,
        speed=args.speed,
    )

    with create_engine(args.engine, verbose=args.verbose) as engine:
        result = engine.synthesize(request)

    print(
        f"[{result.engine}] {result.output_path}\n"
        f"  model={result.model_id}\n"
        f"  {result.sample_rate} Hz / {result.duration_sec:.2f} 秒"
        f" / 生成 {result.elapsed_sec:.2f} 秒"
    )
    return 0


# ---------------------------------------------------------------- batch


def cmd_batch(args: argparse.Namespace) -> int:
    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        raise TTSError(f"入力 JSON が見つかりません: {input_path}")

    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TTSError("入力 JSON はオブジェクトの配列である必要があります。")

    base_dir = input_path.parent
    items = [BatchItem.from_dict(d, i, base_dir) for i, d in enumerate(data)]
    seen: set = set()
    for item in items:
        if item.id in seen:
            raise TTSError(f"id が重複しています: {item.id}")
        seen.add(item.id)

    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    results = []
    failures = []
    started = time.monotonic()

    # 1 プロセスを常駐させて全件を流す。モデルロードは最初の 1 回だけ。
    with create_engine(args.engine, verbose=args.verbose) as engine:
        for index, item in enumerate(items, start=1):
            request = item.to_request(outdir / f"{item.id}.wav")
            label = f"[{index}/{len(items)}] {item.id}"
            try:
                result = engine.synthesize(request)
            # 参照音声が見つからない場合は FileNotFoundError（OSError）が飛ぶ。
            # TTSError だけを捕まえると --keep-going がそこで止まってしまう。
            except (TTSError, OSError, ValueError) as exc:
                print(f"{label} 失敗: {exc}", file=sys.stderr)
                failures.append({"id": item.id, "error": str(exc)})
                if not args.keep_going:
                    break
                continue
            print(f"{label} {result.output_path.name} ({result.elapsed_sec:.2f} 秒)")
            results.append({"id": item.id, "text": item.text, **result.to_dict()})

    manifest = {
        "engine": args.engine,
        "input": str(input_path),
        "total_elapsed_sec": round(time.monotonic() - started, 3),
        "items": results,
        "failures": failures,
    }
    manifest_path = Path(args.outdir).resolve() / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(results)}/{len(items)} 件成功。manifest: {manifest_path}")
    return 1 if failures else 0


# --------------------------------------------------------------- script


def cmd_script(args: argparse.Namespace) -> int:
    script = load_script(Path(args.cast).resolve(), Path(args.script).resolve())
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    engines_used = script.engines_used()
    print(
        f"{len(script.lines)} 台詞 / "
        f"{len(script.voices_used())} キャラクター / "
        f"エンジン: {', '.join(engines_used)}\n"
    )

    # 台詞ごとにプロセスを立て直すとモデルの読み込みを何度も払うことになる。
    # エンジン単位でまとめて処理し、台本順は後で組み直す。
    by_engine: dict = {}
    for line in script.lines:
        by_engine.setdefault(script.cast[line.voice].engine, []).append(line)

    results: dict = {}
    failures = []
    started = time.monotonic()

    for engine_name in engines_used:
        lines = by_engine[engine_name]
        print(f"--- {engine_name} ({len(lines)} 台詞) ---")
        with create_engine(engine_name, verbose=args.verbose) as engine:
            for line in lines:
                request = script.to_request(line, outdir / line.output_name())
                label = f"[{line.index:03d}] {line.voice}"
                try:
                    result = engine.synthesize(request)
                except (TTSError, OSError, ValueError) as exc:
                    print(f"{label} 失敗: {exc}", file=sys.stderr)
                    failures.append(
                        {
                            "index": line.index,
                            "voice": line.voice,
                            "line_no": line.line_no,
                            "error": str(exc),
                        }
                    )
                    if not args.keep_going:
                        return _write_script_manifest(args, script, results, failures, started)
                    continue
                results[line.index] = (line, result)
                preview = (
                    line.text
                    if len(line.text) <= PREVIEW_CHARS
                    else line.text[: PREVIEW_CHARS - 1] + "…"
                )
                print(f"{label} {result.duration_sec:5.2f}秒  {preview}")
        print()

    return _write_script_manifest(args, script, results, failures, started)


def _write_script_manifest(args, script, results: dict, failures: list, started: float) -> int:
    """台本順に並べ直した manifest を書く。

    ``start_sec`` は先頭からの累積オフセット。Remotion 側でそのまま
    <Sequence from=...> の計算に使えるようにしている。
    """
    items = []
    cursor = 0.0
    for line in script.lines:
        found = results.get(line.index)
        if found is None:
            continue
        _, result = found
        items.append(
            {
                "index": line.index,
                "id": line.id,
                "voice": line.voice,
                "text": line.text,
                "start_sec": round(cursor, 3),
                **result.to_dict(),
            }
        )
        cursor += result.duration_sec + args.gap

    manifest = {
        "cast": str(Path(args.cast).resolve()),
        "script": str(Path(args.script).resolve()),
        "gap_sec": args.gap,
        "total_duration_sec": round(max(0.0, cursor - args.gap), 3),
        "total_elapsed_sec": round(time.monotonic() - started, 3),
        "items": items,
        "failures": failures,
    }
    manifest_path = Path(args.outdir).resolve() / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"{len(items)}/{len(script.lines)} 台詞を生成。"
        f"合計 {manifest['total_duration_sec']:.1f} 秒\n"
        f"manifest: {manifest_path}"
    )
    return 1 if failures else 0


# -------------------------------------------------------------- engines


def _cap_cell(spec, cap: Capability) -> str:
    return "○" if spec.supports(cap) else "×"


def cmd_engines(args: argparse.Namespace) -> int:
    specs = available_engines()
    print(f"設定: {config_path()}\n")
    header = f"{'engine':<12} {'状態':<10} {'言語':<10} " + " ".join(
        f"{c.name:<13}" for c in _CAP_ORDER
    )
    print(header)
    print("-" * len(header))
    for name in sorted(specs):
        spec = specs[name]
        state = "構築済み" if spec.installed else "未構築"
        caps = " ".join(f"{_cap_cell(spec, c):<13}" for c in _CAP_ORDER)
        print(f"{name:<12} {state:<10} {','.join(spec.languages):<10} {caps}")

    print()
    for name in sorted(specs):
        spec = specs[name]
        print(f"{name}: {spec.description}")
        print(f"  model : {spec.model_id}")
        print(f"  venv  : {spec.python}")
        if not spec.installed:
            print(f"  → 未構築。docs/setup/{spec.setup_doc} を参照")
    return 0


# --------------------------------------------------------------- doctor


def _probe_engine_torch(spec) -> str:
    """エンジン venv の中で torch と CUDA の状態を調べる。"""
    if not spec.python.is_file():
        return f"venv なし ({spec.python})"
    code = (
        "import json,torch;"
        "print(json.dumps({'torch':torch.__version__,"
        "'cuda':torch.cuda.is_available(),"
        "'device':(torch.cuda.get_device_name(0) if torch.cuda.is_available() else None),"
        "'arch':(list(torch.cuda.get_arch_list()) if torch.cuda.is_available() else [])}))"
    )
    try:
        out = subprocess.run(
            [str(spec.python), "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,  # 戻り値は下で自分で見る
        )
    except subprocess.TimeoutExpired:
        return "torch の読み込みがタイムアウトしました"
    if out.returncode != 0:
        tail = (out.stderr or "").strip().splitlines()[-1:] or ["(詳細なし)"]
        return f"torch の読み込みに失敗: {tail[0]}"

    info = json.loads(out.stdout.strip().splitlines()[-1])
    if not info["cuda"]:
        return f"torch {info['torch']} / CUDA 利用不可（CPU 実行になります）"
    # Blackwell (RTX 50 系) は sm_120。対応アーキに含まれるかまで見る。
    arch_note = ""
    if info["arch"] and not any(a.endswith("_120") for a in info["arch"]):
        arch_note = f"  ※ sm_120 が arch_list に無い: {','.join(info['arch'])}"
    return f"torch {info['torch']} / CUDA OK / {info['device']}{arch_note}"


def cmd_doctor(args: argparse.Namespace) -> int:
    ok = True
    print("== 共通層 ==")
    print(f"python      : {sys.version.split()[0]} ({sys.executable})")
    print(f"project root: {project_root()}")
    print(f"engines.toml: {config_path()}")
    if sys.version_info[:2] != (3, 12):
        print("  ! Python 3.12 を想定しています（mise.toml 参照）")

    print("\n== GPU ==")
    try:
        smi = subprocess.run(
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
            check=False,  # nvidia-smi が無い環境でも続行したい
        )
        print(smi.stdout.strip() if smi.returncode == 0 else "nvidia-smi が失敗しました")
    except (OSError, subprocess.TimeoutExpired):
        print("nvidia-smi が見つかりません（CPU 実行になります）")

    print("\n== エンジン ==")
    for name in sorted(available_engines()):
        spec = get_spec(name)
        print(f"\n[{name}] {spec.model_id}")
        if not spec.installed:
            print(f"  未構築 → docs/setup/{spec.setup_doc}")
            ok = False
            continue
        print(f"  {_probe_engine_torch(spec)}")
    return 0 if ok else 1


# ------------------------------------------------------------------ main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tts_sample",
        description="Qwen3-TTS / Chatterbox / Irodori-TTS を共通インターフェースで使う",
    )
    # --verbose はサブコマンドの前後どちらでも書けるように親パーサで共有する。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-v", "--verbose", action="store_true", help="エンジンの stderr をそのまま表示する"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    names = ", ".join(engine_names())

    p_synth = sub.add_parser("synth", parents=[common], help="1 件を合成する")
    p_synth.add_argument("--engine", required=True, help=f"エンジン名 ({names})")
    src = p_synth.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="合成するテキスト")
    src.add_argument("--text-file", help="テキストを読むファイル (UTF-8)")
    p_synth.add_argument("--out", required=True, help="出力 wav のパス")
    p_synth.add_argument("--lang", choices=["ja", "en"], default=None, help="言語")
    p_synth.add_argument("--ref", default=None, help="参照音声 wav（ゼロショットクローン）")
    p_synth.add_argument(
        "--ref-text", default=None, help="参照音声の書き起こし（Qwen のクローン品質が上がる）"
    )
    p_synth.add_argument(
        "--voice-design",
        default=None,
        help="文章で声を設計する（例: 落ち着いた低めの女性の声。丁寧で穏やか。）",
    )
    p_synth.add_argument("--seed", type=int, default=None, help="乱数シード")
    p_synth.add_argument("--speed", type=float, default=1.0, help="話速（対応エンジンのみ）")
    p_synth.set_defaults(func=cmd_synth)

    p_batch = sub.add_parser("batch", parents=[common], help="JSON の複数件をまとめて合成する")
    p_batch.add_argument("--engine", required=True, help=f"エンジン名 ({names})")
    p_batch.add_argument("--input", required=True, help="入力 JSON")
    p_batch.add_argument("--outdir", required=True, help="出力ディレクトリ")
    p_batch.add_argument("--keep-going", action="store_true", help="1 件失敗しても残りを続行する")
    p_batch.set_defaults(func=cmd_batch)

    p_script = sub.add_parser(
        "script", parents=[common], help="キャラクター台本からまとめて合成する"
    )
    p_script.add_argument("--cast", required=True, help="キャスト定義 TOML")
    p_script.add_argument("--script", required=True, help="台本テキスト (UTF-8)")
    p_script.add_argument("--outdir", required=True, help="出力ディレクトリ")
    p_script.add_argument(
        "--gap",
        type=float,
        default=0.3,
        help="manifest の start_sec を計算するときの台詞間の間（秒、既定 0.3）",
    )
    p_script.add_argument(
        "--keep-going", action="store_true", help="1 台詞失敗しても残りを続行する"
    )
    p_script.set_defaults(func=cmd_script)

    p_engines = sub.add_parser("engines", parents=[common], help="エンジン一覧とケイパビリティ")
    p_engines.set_defaults(func=cmd_engines)

    p_doctor = sub.add_parser("doctor", parents=[common], help="環境の健全性チェック")
    p_doctor.set_defaults(func=cmd_doctor)

    return parser


def _force_utf8_io() -> None:
    """自分の標準出力を UTF-8 に固定する。

    Windows の既定は cp932 で、パイプへ出すと日本語も '—' のような記号も
    UnicodeEncodeError になる。エンジン側のパイプは subprocess_engine 側で
    別途 UTF-8 に固定している。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


def main(argv: list | None = None) -> int:
    _force_utf8_io()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except TTSError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n中断しました。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
