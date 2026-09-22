"""キャラクター台本の読み込み。

呼ばれる先: core.tts_service のみ (`core` の外からは import しない)
呼ぶ先: core.settings, engine._shared.protocol

台本は 2 つのファイルに分ける。

    cast.toml     キャラクターの声の定義。一度書けば使い回す。
    script.txt    台詞そのもの。脚本と同じ「話者: 台詞」の形式。

台詞を書くのは毎回、声を決めるのは最初の一度きりなので、書く量が最小に
なるようこの分担にしている。

台本の文法 (すべて UTF-8):

    # 行頭の # はコメント。セクションの見出しにも使う。

    霊夢: 今日はいい天気ね。
    魔理沙: ぜんぜんダメだぜ！

    [001-001-plasmo] Plasmo: Hello everyone!
    霊夢[speed=0.9]: ゆっくり話すわ。
    魔理沙[id=punchline]: それでもいいのか？

    霊夢: 長い台詞は
      インデントした行で続けられる。

角括弧で指定できるのは `id` / `speed` / `seed` / `lang` / `volume`。継続行は
**区切り文字なしで連結される**ので、英語の台詞は 1 行に収めるか行末に
空白を置くこと (日本語で余計な空白が入らないようにこうしている)。
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field

from ttstoolkit.core.settings import TTSToolkitError
from ttstoolkit.engine._shared.protocol import SynthesisRequest

# 「話者: 台詞」。話者名のあとに省略可能な [key=value, ...] を書ける。
# コロンは半角でも全角でもよい。
_LINE_RE = re.compile(
    r"^(?P<voice>[^:：\[\]]+?)"
    r"(?:\[(?P<options>[^\]]*)\])?"
    r"\s*[:：]\s*"
    r"(?P<text>.*)$"
)

# 行頭の [出力名]。拡張子は出力時に .wav を補う。
_OUTPUT_NAME_RE = re.compile(r"^\[(?P<output_name>[^\[\]]+)\]\s*")

# 台詞の行に書けるオプション
_LINE_OPTION_KEYS = ("id", "speed", "seed", "lang", "volume")

# cast.toml の 1 キャラクターに書けるキー
_CAST_KEYS = (
    "engine",
    "reference_audio",
    "reference_text",
    "voice_design",
    "language",
    "seed",
    "speed",
    "volume",
)


class ScriptError(TTSToolkitError):
    """台本またはキャスト定義の書式が正しくない。"""


@dataclass(frozen=True)
class Voice:
    """cast.toml の 1 キャラクター。

    Attributes:
        name: キャラクター名。台本の話者名と突き合わせる。
        engine: 使うエンジン名。
        reference_audio: 声を真似る参照音声のパス。
        reference_text: 参照音声の書き起こし。
        voice_design: 文章による声の指定。
        language: 言語コード。
        seed: 乱数シード。
        speed: 話速。
        volume: 音量。
    """

    name: str
    engine: str
    reference_audio: str | None = None
    reference_text: str | None = None
    voice_design: str | None = None
    language: str | None = None
    seed: int | None = None
    speed: float = 1.0
    volume: float = 1.0


@dataclass(frozen=True)
class ScriptLine:
    """台本の 1 台詞。

    Attributes:
        index: 台本中の並び順 (1 始まり)。
        voice: 話者名。
        text: 読み上げるテキスト。
        line_no: 台本内の行番号 (エラーメッセージ用)。
        output_name_override: 行頭で指定された出力ファイル名（拡張子なし）。
        id: 出力ファイル名に使う識別子。
        language: この台詞だけの言語コード。
        seed: この台詞だけの乱数シード。
        speed: この台詞だけの話速。
        volume: この台詞だけの音量。
    """

    index: int
    voice: str
    text: str
    line_no: int
    output_name_override: str | None = None
    id: str | None = None
    language: str | None = None
    seed: int | None = None
    speed: float | None = None
    volume: float | None = None

    def output_name(self) -> str:
        """出力 wav のファイル名を返す。

        並び順が一目で分かるよう連番を前に置く。

        Returns:
            str: ファイル名 (ディレクトリは含まない)。
        """
        if self.output_name_override:
            return f"{self.output_name_override}.wav"
        suffix = self.id if self.id else self.voice
        return f"{self.index:03d}-{suffix}.wav"


@dataclass
class Script:
    """台本全体。

    Attributes:
        lines: 台詞の一覧。
        cast: キャラクター名 -> 声の定義。
        source: 読み込んだ台本のパス。
    """

    lines: list[ScriptLine] = field(default_factory=list)
    cast: dict[str, Voice] = field(default_factory=dict)
    source: str | None = None

    def voices_used(self) -> list[str]:
        """台本に登場する話者名を、登場順に重複なく返す。"""
        seen: list[str] = []
        for line in self.lines:
            if line.voice not in seen:
                seen.append(line.voice)
        return seen

    def engines_used(self) -> list[str]:
        """台本で使うエンジン名を、登場順に重複なく返す。"""
        seen: list[str] = []
        for name in self.voices_used():
            engine = self.cast[name].engine
            if engine not in seen:
                seen.append(engine)
        return seen

    def to_request(
        self, line: ScriptLine, output_path: str
    ) -> SynthesisRequest:
        """1 台詞を、その話者の声の設定と合わせて合成リクエストにする。

        Args:
            line: 台詞。
            output_path: 書き出す wav のパス。

        Returns:
            SynthesisRequest: 合成リクエスト。
        """
        voice = self.cast[line.voice]
        return SynthesisRequest(
            text=line.text,
            output_path=output_path,
            language=line.language or voice.language,
            reference_audio=voice.reference_audio,
            reference_text=voice.reference_text,
            voice_design=voice.voice_design,
            seed=line.seed if line.seed is not None else voice.seed,
            speed=line.speed if line.speed is not None else voice.speed,
            volume=(line.volume if line.volume is not None else voice.volume),
        )


def parse_cast(path: str) -> dict[str, Voice]:
    """cast.toml を読んで キャラクター名 -> Voice を返す。

    キャラクター名が日本語のときは TOML のテーブル名をクォートする::

        [voices."霊夢"]
        engine = "irodori"
        reference_audio = "../voices/reimu.wav"

    Args:
        path: cast.toml のパス。

    Returns:
        dict[str, Voice]: キャラクター名 -> 声の定義。

    Raises:
        ScriptError: ファイルが無い、または書式が正しくないとき。
    """
    if not os.path.isfile(path):
        raise ScriptError(f"Cast file not found: {path}")

    try:
        with open(path, "rb") as file:
            raw = tomllib.load(file)
    except tomllib.TOMLDecodeError as e:
        raise ScriptError(f"{path} is not valid TOML: {e}") from e

    table = raw.get("voices")
    if not isinstance(table, dict) or not table:
        raise ScriptError(
            f'{path} has no [voices."<name>"] section. '
            'Example: [voices."霊夢"] with engine = "irodori"'
        )

    base_dir = os.path.dirname(os.path.abspath(path))
    cast: dict[str, Voice] = {}
    for name, entry in table.items():
        cast[name] = _build_voice(path, name, entry, base_dir)
    return cast


def _build_voice(path: str, name: str, entry: object, base_dir: str) -> Voice:
    """cast.toml の 1 エントリを Voice にする。

    Args:
        path: cast.toml のパス (エラーメッセージ用)。
        name: キャラクター名。
        entry: TOML のテーブル。
        base_dir: 参照音声の相対パスを解決する基準。

    Returns:
        Voice: 声の定義。

    Raises:
        ScriptError: テーブルでない、未知のキーがある、engine が無いとき。
    """
    if not isinstance(entry, dict):
        raise ScriptError(f'{path}: [voices."{name}"] must be a table')

    unknown = sorted(set(entry) - set(_CAST_KEYS))
    if unknown:
        raise ScriptError(
            f'{path}: [voices."{name}"] has unknown keys: '
            f"{', '.join(unknown)} (allowed: {', '.join(_CAST_KEYS)})"
        )
    if "engine" not in entry:
        raise ScriptError(f'{path}: [voices."{name}"] has no engine')

    reference = entry.get("reference_audio")
    return Voice(
        name=name,
        engine=str(entry["engine"]),
        # 参照音声は cast.toml からの相対パスで解決する
        reference_audio=(
            os.path.abspath(os.path.join(base_dir, reference))
            if reference
            else None
        ),
        reference_text=entry.get("reference_text"),
        voice_design=entry.get("voice_design"),
        language=entry.get("language"),
        seed=entry.get("seed"),
        speed=float(entry.get("speed", 1.0)),
        volume=float(entry.get("volume", 1.0)),
    )


def _parse_line_options(raw: str, line_no: int) -> dict[str, str]:
    """台詞の行の角括弧の中を解釈する。

    Args:
        raw: 角括弧の中身。
        line_no: 台本内の行番号 (エラーメッセージ用)。

    Returns:
        dict[str, str]: キー -> 値。

    Raises:
        ScriptError: key=value の形でない、または未知のキーのとき。
    """
    options: dict[str, str] = {}
    for raw_chunk in raw.split(","):
        chunk = raw_chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ScriptError(
                f"Line {line_no}: options must be key=value ({chunk!r})"
            )
        key, _, value = chunk.partition("=")
        key = key.strip()
        if key not in _LINE_OPTION_KEYS:
            raise ScriptError(
                f"Line {line_no}: unknown option {key!r} "
                f"(allowed: {', '.join(_LINE_OPTION_KEYS)})"
            )
        options[key] = value.strip()
    return options


def _parse_output_name(raw: str, line_no: int) -> str:
    """行頭の出力名を Windows で使えるファイル名として検証する。"""
    name = raw.strip()
    if not name:
        raise ScriptError(f"Line {line_no}: output name is empty")
    if any(char in name for char in '<>:"/\\|?*'):
        raise ScriptError(
            f"Line {line_no}: output name contains an invalid filename character"
        )
    if name.endswith((".", " ")):
        raise ScriptError(
            f"Line {line_no}: output name must not end with a period or space"
        )
    return name


def parse_script(path: str, cast: dict[str, Voice]) -> Script:
    """台本テキストを読み、キャスト定義と突き合わせて Script を返す。

    Args:
        path: 台本テキストのパス。
        cast: キャラクター名 -> 声の定義。

    Returns:
        Script: 読み込んだ台本。

    Raises:
        ScriptError: ファイルが無い、または書式が正しくないとき。
    """
    if not os.path.isfile(path):
        raise ScriptError(f"Script file not found: {path}")

    lines: list[ScriptLine] = []
    pending: list[dict] = []

    def flush() -> None:
        """溜めていた継続行をひとつの台詞にまとめる。"""
        if not pending:
            return
        head = pending[0]
        text = (head["text"] + "".join(pending[1:])).strip()
        if not text:
            raise ScriptError(f"Line {head['line_no']}: the line is empty")
        options = head["options"]
        lines.append(
            ScriptLine(
                index=len(lines) + 1,
                voice=head["voice"],
                text=text,
                line_no=head["line_no"],
                output_name_override=head["output_name_override"],
                id=options.get("id"),
                language=options.get("lang"),
                seed=int(options["seed"]) if "seed" in options else None,
                speed=(
                    float(options["speed"]) if "speed" in options else None
                ),
                volume=(
                    float(options["volume"]) if "volume" in options else None
                ),
            )
        )
        pending.clear()

    with open(path, encoding="utf-8") as file:
        source_lines = file.read().splitlines()

    for line_no, raw in enumerate(source_lines, start=1):
        stripped = raw.strip()

        if stripped.startswith("#"):
            continue
        if not stripped:
            flush()
            continue

        # インデントされていて直前に台詞があれば、継続行として連結する
        if pending and raw[:1] in (" ", "\t"):
            pending.append(stripped)
            continue

        output_name_override = None
        output_match = _OUTPUT_NAME_RE.match(stripped)
        if output_match is not None:
            output_name_override = _parse_output_name(
                output_match.group("output_name"), line_no
            )
            stripped = stripped[output_match.end() :]

        match = _LINE_RE.match(stripped)
        if match is None:
            raise ScriptError(
                f"Line {line_no} could not be parsed: {stripped[:60]!r} "
                "(write it as '<voice>: <line>')"
            )

        flush()
        voice = match.group("voice").strip()
        if voice not in cast:
            raise ScriptError(
                f"Line {line_no}: {voice!r} is not in the cast "
                f"(defined: {', '.join(cast)})"
            )
        pending.append(
            {
                "voice": voice,
                "text": match.group("text"),
                "line_no": line_no,
                "output_name_override": output_name_override,
                "options": _parse_line_options(
                    match.group("options") or "", line_no
                ),
            }
        )

    flush()

    if not lines:
        raise ScriptError(f"{path} has no lines")

    ids = [line.id for line in lines if line.id]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ScriptError(f"Duplicated ids: {', '.join(duplicates)}")

    output_names = [line.output_name() for line in lines]
    normalized_output_names = [os.path.normcase(name) for name in output_names]
    duplicate_output_names = sorted(
        {
            name
            for name, normalized_name in zip(
                output_names, normalized_output_names, strict=True
            )
            if normalized_output_names.count(normalized_name) > 1
        }
    )
    if duplicate_output_names:
        raise ScriptError(
            f"Duplicated output names: {', '.join(duplicate_output_names)}"
        )

    return Script(lines=lines, cast=cast, source=os.path.abspath(path))


def load_script(cast_path: str, script_path: str) -> Script:
    """キャスト定義と台本をまとめて読み込む。

    Args:
        cast_path: cast.toml のパス。
        script_path: 台本テキストのパス。

    Returns:
        Script: 読み込んだ台本。

    Raises:
        ScriptError: どちらかのファイルが無い、または書式が正しくないとき。
    """
    return parse_script(script_path, parse_cast(cast_path))
