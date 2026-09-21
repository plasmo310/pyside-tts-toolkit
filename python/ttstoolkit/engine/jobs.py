"""まとめて合成する処理 (バッチと台本) と、その manifest の書き出し。

CLI からも GUI からも同じものを呼べるようにここに置く。画面出力も
プロセス終了もせず、進捗は `on_progress` へ、失敗は `TTSToolkitError`
で返す。

どちらの処理も 1 つの runner を常駐させたまま全件を流すので、モデルの
ロード (10〜60 秒) は最初の 1 回しか払わない。台本は話者ごとにエンジン
が違いうるので、エンジン単位でまとめてから台本順に組み直す。
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ttstoolkit.engine.registry import create_engine
from ttstoolkit.engine.script import Script, ScriptLine
from ttstoolkit.engine.settings import TTSToolkitError, get_logger
from ttstoolkit.engine.types import (
    BatchItem,
    SynthesisResult,
)

_logger = get_logger(__name__)

# manifest のファイル名 (バッチも台本も同じ)
MANIFEST_NAME = "manifest.json"

# 進捗表示で台詞を切り詰める幅
_PREVIEW_CHARS = 24

# 進捗 1 行を受け取る関数と、キャンセルされたかを返す関数
ProgressFunc = Callable[[str], None]
CancelFunc = Callable[[], bool]


class JobCanceledError(TTSToolkitError):
    """利用者が途中で止めた。"""


@dataclass
class JobOutcome:
    """まとめて合成した結果。

    Attributes:
        written_paths: 書き出した wav のパス。
        manifest_path: 書き出した manifest のパス。
        failures: 失敗した件の記録。
        total_count: 処理しようとした件数。
        is_canceled: 途中で止めたか。
    """

    written_paths: list[str] = field(default_factory=list)
    manifest_path: str | None = None
    failures: list[dict] = field(default_factory=list)
    total_count: int = 0
    is_canceled: bool = False


def _no_progress(message: str) -> None:
    """進捗を捨てる既定の関数。"""


def _never_canceled() -> bool:
    """キャンセルされないことにする既定の関数。"""
    return False


def _write_manifest(output_dir: str, manifest: dict) -> str:
    """manifest を書き出してパスを返す。

    Args:
        output_dir: 書き出し先ディレクトリ。
        manifest: 書き出す内容。

    Returns:
        str: 書き出した manifest のパス。
    """
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, MANIFEST_NAME)
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
        file.write("\n")
    _logger.info("wrote %s", path)
    return path


def _preview(text: str) -> str:
    """進捗表示用に台詞を切り詰める。

    Args:
        text: 元のテキスト。

    Returns:
        str: 切り詰めたテキスト。
    """
    if len(text) <= _PREVIEW_CHARS:
        return text
    return text[: _PREVIEW_CHARS - 1] + "…"


def load_batch_items(path: str) -> list[BatchItem]:
    """バッチ入力 JSON を読む。

    Args:
        path: 入力 JSON のパス。

    Returns:
        list[BatchItem]: 読み込んだ項目。

    Raises:
        TTSToolkitError: 読めない、形が違う、id が重複しているとき。
    """
    if not os.path.isfile(path):
        raise TTSToolkitError(f"Batch input not found: {path}")

    with open(path, encoding="utf-8") as file:
        try:
            data = json.load(file)
        except json.JSONDecodeError as e:
            raise TTSToolkitError(f"{path} is not valid JSON: {e}") from e

    if not isinstance(data, list):
        raise TTSToolkitError(f"{path} must contain an array of objects")

    base_dir = os.path.dirname(os.path.abspath(path))
    items = [
        BatchItem.from_dict(entry, index, base_dir)
        for index, entry in enumerate(data)
    ]

    seen: set[str] = set()
    for item in items:
        if item.id in seen:
            raise TTSToolkitError(f"Duplicated id: {item.id}")
        seen.add(item.id)
    return items


def run_batch(
    engine_name: str,
    items: list[BatchItem],
    output_dir: str,
    keep_going: bool = False,
    verbose: bool = False,
    on_progress: ProgressFunc = _no_progress,
    is_canceled: CancelFunc = _never_canceled,
) -> JobOutcome:
    """バッチ入力をまとめて合成する。

    Args:
        engine_name: 使うエンジン名。
        items: 合成する項目。
        output_dir: 書き出し先ディレクトリ。
        keep_going: 1 件失敗しても残りを続けるか。
        verbose: エンジン自身の出力もログへ流すか。
        on_progress: 進捗 1 行ぶんを受け取る関数。
        is_canceled: 途中で止められたかを返す関数。

    Returns:
        JobOutcome: 書き出したパスと失敗の記録。
    """
    outcome = JobOutcome(total_count=len(items))
    results: list[dict] = []
    started = time.monotonic()

    with create_engine(engine_name, verbose=verbose) as engine:
        for index, item in enumerate(items, start=1):
            if is_canceled():
                outcome.is_canceled = True
                break
            label = f"[{index}/{len(items)}] {item.id}"
            request = item.to_request(
                os.path.join(output_dir, f"{item.id}.wav")
            )
            try:
                result = engine.synthesize(request)
            except (TTSToolkitError, OSError, ValueError) as e:
                on_progress(f"{label} failed: {e}")
                outcome.failures.append({"id": item.id, "error": str(e)})
                if not keep_going:
                    break
                continue
            on_progress(
                f"{label} {result.duration_sec:5.2f}s  {_preview(item.text)}"
            )
            outcome.written_paths.append(result.output_path)
            results.append(
                {"id": item.id, "text": item.text, **result.to_dict()}
            )

    outcome.manifest_path = _write_manifest(
        output_dir,
        {
            "engine": engine_name,
            "total_elapsed_sec": round(time.monotonic() - started, 3),
            "items": results,
            "failures": outcome.failures,
        },
    )
    return outcome


def run_script(
    script: Script,
    output_dir: str,
    gap_sec: float = 0.3,
    keep_going: bool = False,
    verbose: bool = False,
    on_progress: ProgressFunc = _no_progress,
    is_canceled: CancelFunc = _never_canceled,
) -> JobOutcome:
    """台本をまとめて合成する。

    台詞ごとにプロセスを立て直すとモデルの読み込みを何度も払うので、
    エンジン単位でまとめて処理し、台本順は manifest で組み直す。

    Args:
        script: 読み込み済みの台本。
        output_dir: 書き出し先ディレクトリ。
        gap_sec: manifest の `start_sec` を出すときの台詞間の間 (秒)。
        keep_going: 1 台詞失敗しても残りを続けるか。
        verbose: エンジン自身の出力もログへ流すか。
        on_progress: 進捗 1 行ぶんを受け取る関数。
        is_canceled: 途中で止められたかを返す関数。

    Returns:
        JobOutcome: 書き出したパスと失敗の記録。
    """
    outcome = JobOutcome(total_count=len(script.lines))
    results: dict[int, SynthesisResult] = {}
    started = time.monotonic()

    by_engine: dict[str, list[ScriptLine]] = {}
    for line in script.lines:
        by_engine.setdefault(script.cast[line.voice].engine, []).append(line)

    for engine_name in script.engines_used():
        lines = by_engine[engine_name]
        on_progress(f"--- {engine_name} ({len(lines)} lines) ---")
        stop = _run_script_engine(
            engine_name,
            lines,
            script,
            output_dir,
            results,
            outcome,
            keep_going,
            verbose,
            on_progress,
            is_canceled,
        )
        if stop:
            break

    outcome.manifest_path = _write_manifest(
        output_dir,
        _build_script_manifest(
            script, results, outcome.failures, gap_sec, started
        ),
    )
    return outcome


def _run_script_engine(
    engine_name: str,
    lines: list[ScriptLine],
    script: Script,
    output_dir: str,
    results: dict[int, SynthesisResult],
    outcome: JobOutcome,
    keep_going: bool,
    verbose: bool,
    on_progress: ProgressFunc,
    is_canceled: CancelFunc,
) -> bool:
    """1 つのエンジンが担当する台詞をまとめて合成する。

    Args:
        engine_name: 使うエンジン名。
        lines: このエンジンが担当する台詞。
        script: 読み込み済みの台本。
        output_dir: 書き出し先ディレクトリ。
        results: 台詞の並び順 -> 合成結果。ここへ書き足す。
        outcome: 失敗と書き出しを記録する先。
        keep_going: 1 台詞失敗しても残りを続けるか。
        verbose: エンジン自身の出力もログへ流すか。
        on_progress: 進捗 1 行ぶんを受け取る関数。
        is_canceled: 途中で止められたかを返す関数。

    Returns:
        bool: 残りのエンジンに進まず打ち切るなら True。
    """
    with create_engine(engine_name, verbose=verbose) as engine:
        for line in lines:
            if is_canceled():
                outcome.is_canceled = True
                return True
            label = f"[{line.index:03d}] {line.voice}"
            request = script.to_request(
                line, os.path.join(output_dir, line.output_name())
            )
            try:
                result = engine.synthesize(request)
            except (TTSToolkitError, OSError, ValueError) as e:
                on_progress(f"{label} failed: {e}")
                outcome.failures.append(
                    {
                        "index": line.index,
                        "voice": line.voice,
                        "line_no": line.line_no,
                        "error": str(e),
                    }
                )
                if not keep_going:
                    return True
                continue
            on_progress(
                f"{label} {result.duration_sec:5.2f}s  {_preview(line.text)}"
            )
            results[line.index] = result
            outcome.written_paths.append(result.output_path)
    return False


def _build_script_manifest(
    script: Script,
    results: dict[int, SynthesisResult],
    failures: list[dict],
    gap_sec: float,
    started: float,
) -> dict:
    """台本順に並べ直した manifest を組み立てる。

    `start_sec` は先頭からの累積オフセット。動画側でそのまま
    「この秒から流す」の計算に使えるようにしている。

    Args:
        script: 読み込み済みの台本。
        results: 台詞の並び順 -> 合成結果。
        failures: 失敗した件の記録。
        gap_sec: 台詞間の間 (秒)。
        started: 処理を始めた時刻 (time.monotonic 基準)。

    Returns:
        dict: manifest の中身。
    """
    items: list[dict] = []
    cursor = 0.0
    for line in script.lines:
        result = results.get(line.index)
        if result is None:
            continue
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
        cursor += result.duration_sec + gap_sec

    return {
        "script": script.source,
        "gap_sec": gap_sec,
        "total_duration_sec": round(max(0.0, cursor - gap_sec), 3),
        "total_elapsed_sec": round(time.monotonic() - started, 3),
        "items": items,
        "failures": failures,
    }
