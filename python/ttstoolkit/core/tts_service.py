"""core の入口 ── CLI / GUI はここに「実行」を頼む。

呼ばれる先: cli/commands.py, gui/main_model.py
呼ぶ先: core.engine, core.paths, core.settings,
        core._internal.engine_process, core._internal.script

1 件の合成も、バッチも、台本も、すべて `TTSService` のメソッドとして
並ぶ。CLI からも GUI からも同じものを呼ぶので、画面出力もプロセス終了も
せず、進捗は `on_progress` へ、失敗は `TTSToolkitError` で返す。

    service = TTSService(verbose=True)
    outcome = service.run_script("cast.toml", "ep01.txt", "output/ep01")

どのまとめ処理も 1 つの runner を常駐させたまま全件を流すので、モデルの
ロード (10〜60 秒) は最初の 1 回しか払わない。台本は話者ごとにエンジン
が違いうるので、エンジン単位でまとめてから台本順に組み直す。

エンジンの一覧や対応機能を「調べるだけ」なら、ここを通さず
`core.engine` を直接見る。
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ttstoolkit.core._internal.engine_process import create_engine
from ttstoolkit.core._internal.script import Script, ScriptLine, load_script
from ttstoolkit.core._internal.script_player import write_script_player
from ttstoolkit.core.engine import SynthesisResult
from ttstoolkit.core.settings import TTSToolkitError, get_logger
from ttstoolkit.engine._shared.protocol import SynthesisRequest

_logger = get_logger(__name__)

# manifest のファイル名 (バッチも台本も同じ)
MANIFEST_NAME = "manifest.json"

# 進捗表示で台詞を切り詰める幅
_PREVIEW_CHARS = 24

# 進捗 1 行を受け取る関数と、キャンセルされたかを返す関数
ProgressFunc = Callable[[str], None]
CancelFunc = Callable[[], bool]


def _no_progress(message: str) -> None:
    """進捗を捨てる既定の関数。"""


def _never_canceled() -> bool:
    """キャンセルされないことにする既定の関数。"""
    return False


@dataclass(frozen=True)
class BatchItem:
    """バッチ入力 JSON の 1 要素。

    Attributes:
        id: 出力ファイル名に使う識別子。
        text: 読み上げるテキスト。
        language: 言語コード。
        reference_audio: 参照音声のパス。
        reference_text: 参照音声の書き起こし。
        voice_design: 文章による声の指定。
        seed: 乱数シード。
        speed: 話速。
    """

    id: str
    text: str
    language: str | None = None
    reference_audio: str | None = None
    reference_text: str | None = None
    voice_design: str | None = None
    seed: int | None = None
    speed: float = 1.0

    @classmethod
    def from_dict(cls, data: dict, index: int, base_dir: str) -> BatchItem:
        """JSON の 1 要素から作る。

        Args:
            data: JSON の 1 要素。
            index: 配列中の位置。エラーメッセージと既定 id に使う。
            base_dir: 参照音声の相対パスを解決する基準。

        Returns:
            BatchItem: 変換した 1 要素。

        Raises:
            ValueError: text が無いとき。
        """
        if "text" not in data:
            raise ValueError(f"Batch item {index} has no text")
        reference = data.get("reference_audio")
        return cls(
            id=str(data.get("id", f"item-{index:04d}")),
            text=str(data["text"]),
            language=data.get("language"),
            reference_audio=(
                os.path.abspath(os.path.join(base_dir, reference))
                if reference
                else None
            ),
            reference_text=data.get("reference_text"),
            voice_design=data.get("voice_design"),
            seed=data.get("seed"),
            speed=float(data.get("speed", 1.0)),
        )

    def to_request(self, output_path: str) -> SynthesisRequest:
        """書き出し先を決めて合成リクエストにする。

        Args:
            output_path: 書き出す wav のパス。

        Returns:
            SynthesisRequest: 合成リクエスト。
        """
        return SynthesisRequest(
            text=self.text,
            output_path=output_path,
            language=self.language,
            reference_audio=self.reference_audio,
            reference_text=self.reference_text,
            voice_design=self.voice_design,
            seed=self.seed,
            speed=self.speed,
        )


@dataclass
class JobOutcome:
    """まとめて合成した結果。

    Attributes:
        written_paths: 書き出した wav のパス。
        manifest_path: 書き出した manifest のパス。
        player_path: 書き出した再生用 HTML のパス。台本のときだけ入る。
        failures: 失敗した件の記録。
        total_count: 処理しようとした件数。
        is_canceled: 途中で止めたか。
    """

    written_paths: list[str] = field(default_factory=list)
    manifest_path: str | None = None
    player_path: str | None = None
    failures: list[dict] = field(default_factory=list)
    total_count: int = 0
    is_canceled: bool = False


@dataclass
class _ScriptRun:
    """台本 1 回ぶんの実行状態。エンジンをまたいで持ち回る。

    エンジンごとの処理に引数を 10 個渡す代わりに、変わらないものと
    書き足していくものをここにまとめる。

    Attributes:
        script: 読み込み済みの台本。
        output_dir: 書き出し先ディレクトリ。
        keep_going: 1 台詞失敗しても残りを続けるか。
        on_progress: 進捗 1 行ぶんを受け取る関数。
        is_canceled: 途中で止められたかを返す関数。
        outcome: 失敗と書き出しを記録する先。
        results: 台詞の並び順 -> 合成結果。
    """

    script: Script
    output_dir: str
    keep_going: bool
    on_progress: ProgressFunc
    is_canceled: CancelFunc
    outcome: JobOutcome
    results: dict[int, SynthesisResult] = field(default_factory=dict)


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


def _player_title(output_dir: str) -> str:
    """再生用 HTML のタイトルを書き出し先ディレクトリ名から作る。

    Args:
        output_dir: 書き出し先ディレクトリ。

    Returns:
        str: ページタイトルに使う文字列。
    """
    name = os.path.basename(os.path.normpath(output_dir))
    return name.replace("_", " ")


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


class TTSService:
    """CLI / GUI から合成を頼むための入口。

    Attributes:
        __verbose (bool): エンジン自身の出力もログへ流すか。
    """

    def __init__(self, verbose: bool = False) -> None:
        """サービスを作る（この時点ではモデルをロードしない）。

        Args:
            verbose: エンジン自身の出力もログへ流すか。
        """
        self.__verbose = verbose

    # ------------------------------------------------------------------
    # 1 件だけ
    # ------------------------------------------------------------------

    def synthesize(
        self, engine_name: str, request: SynthesisRequest
    ) -> SynthesisResult:
        """1 件を合成して書き出す。

        Args:
            engine_name: 使うエンジン名。
            request: 合成リクエスト。

        Returns:
            SynthesisResult: 合成結果。

        Raises:
            TTSToolkitError: 検証に失敗した、または合成が失敗したとき。
        """
        with create_engine(engine_name, verbose=self.__verbose) as engine:
            return engine.synthesize(request)

    # ------------------------------------------------------------------
    # バッチ
    # ------------------------------------------------------------------

    def run_batch(
        self,
        engine_name: str,
        input_path: str,
        output_dir: str,
        keep_going: bool = False,
        on_progress: ProgressFunc = _no_progress,
        is_canceled: CancelFunc = _never_canceled,
    ) -> JobOutcome:
        """バッチ入力 JSON を読んで、まとめて合成する。

        Args:
            engine_name: 使うエンジン名。
            input_path: 入力 JSON のパス (実在すること)。
            output_dir: 書き出し先ディレクトリ。
            keep_going: 1 件失敗しても残りを続けるか。
            on_progress: 進捗 1 行ぶんを受け取る関数。
            is_canceled: 途中で止められたかを返す関数。

        Returns:
            JobOutcome: 書き出したパスと失敗の記録。

        Raises:
            TTSToolkitError: 入力 JSON が読めない、または形が違うとき。
        """
        items = load_batch_items(input_path)
        _logger.info("%d items from %s", len(items), input_path)

        outcome = JobOutcome(total_count=len(items))
        results: list[dict] = []
        started = time.monotonic()

        with create_engine(engine_name, verbose=self.__verbose) as engine:
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
                    f"{label} {result.duration_sec:5.2f}s  "
                    f"{_preview(item.text)}"
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

    # ------------------------------------------------------------------
    # 台本
    # ------------------------------------------------------------------

    def run_script(
        self,
        cast_path: str,
        script_path: str,
        output_dir: str,
        gap_sec: float = 0.3,
        keep_going: bool = False,
        on_progress: ProgressFunc = _no_progress,
        is_canceled: CancelFunc = _never_canceled,
    ) -> JobOutcome:
        """キャスト定義と台本を読んで、まとめて合成する。

        台詞ごとにプロセスを立て直すとモデルの読み込みを何度も払うので、
        エンジン単位でまとめて処理し、台本順は manifest で組み直す。

        Args:
            cast_path: cast.toml のパス (実在すること)。
            script_path: 台本テキストのパス (実在すること)。
            output_dir: 書き出し先ディレクトリ。
            gap_sec: manifest の `start_sec` を出すときの台詞間の間 (秒)。
            keep_going: 1 台詞失敗しても残りを続けるか。
            on_progress: 進捗 1 行ぶんを受け取る関数。
            is_canceled: 途中で止められたかを返す関数。

        Returns:
            JobOutcome: 書き出したパスと失敗の記録。

        Raises:
            ScriptError: 台本またはキャスト定義が読めないとき。
        """
        script = load_script(cast_path, script_path)
        _logger.info(
            "%d lines / %d characters / engines: %s",
            len(script.lines),
            len(script.voices_used()),
            ", ".join(script.engines_used()),
        )

        run = _ScriptRun(
            script=script,
            output_dir=output_dir,
            keep_going=keep_going,
            on_progress=on_progress,
            is_canceled=is_canceled,
            outcome=JobOutcome(total_count=len(script.lines)),
        )
        started = time.monotonic()

        by_engine: dict[str, list[ScriptLine]] = {}
        for line in script.lines:
            engine_name = script.cast[line.voice].engine
            by_engine.setdefault(engine_name, []).append(line)

        for engine_name in script.engines_used():
            lines = by_engine[engine_name]
            on_progress(f"--- {engine_name} ({len(lines)} lines) ---")
            if self.__run_script_engine(run, engine_name, lines):
                break

        manifest = _build_script_manifest(
            script, run.results, run.outcome.failures, gap_sec, started
        )
        run.outcome.manifest_path = _write_manifest(output_dir, manifest)
        run.outcome.player_path = write_script_player(
            output_dir, _player_title(output_dir), manifest
        )
        return run.outcome

    def __run_script_engine(
        self, run: _ScriptRun, engine_name: str, lines: list[ScriptLine]
    ) -> bool:
        """1 つのエンジンが担当する台詞をまとめて合成する。

        Args:
            run: 台本 1 回ぶんの実行状態。結果をここへ書き足す。
            engine_name: 使うエンジン名。
            lines: このエンジンが担当する台詞。

        Returns:
            bool: 残りのエンジンに進まず打ち切るなら True。
        """
        outcome = run.outcome
        with create_engine(engine_name, verbose=self.__verbose) as engine:
            for line in lines:
                if run.is_canceled():
                    outcome.is_canceled = True
                    return True
                label = f"[{line.index:03d}] {line.voice}"
                request = run.script.to_request(
                    line, os.path.join(run.output_dir, line.output_name())
                )
                try:
                    result = engine.synthesize(request)
                except (TTSToolkitError, OSError, ValueError) as e:
                    run.on_progress(f"{label} failed: {e}")
                    outcome.failures.append(
                        {
                            "index": line.index,
                            "voice": line.voice,
                            "line_no": line.line_no,
                            "error": str(e),
                        }
                    )
                    if not run.keep_going:
                        return True
                    continue
                run.on_progress(
                    f"{label} {result.duration_sec:5.2f}s  "
                    f"{_preview(line.text)}"
                )
                run.results[line.index] = result
                outcome.written_paths.append(result.output_path)
        return False
