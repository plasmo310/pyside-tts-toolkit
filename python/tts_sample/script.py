"""キャラクター台本の読み込み。

台本は 2 つのファイルに分ける。

  cast.toml     キャラクターの声の定義。一度書けば使い回す。
  script.txt    台詞そのもの。脚本と同じ「話者: 台詞」の形式。

台詞を書くのは毎回、声を決めるのは最初の一度きりなので、
書く量が最小になるようこの分担にしている。

台本の文法（すべて UTF-8）:

    # 行頭の # はコメント。セクションの見出しにも使う。

    霊夢: 今日はいい天気ね。
    魔理沙: ぜんぜんダメだぜ！

    霊夢[speed=0.9]: ゆっくり話すわ。
    魔理沙[id=punchline]: それでもいいのか？

    霊夢: 長い台詞は
      インデントした行で続けられる。

角括弧で指定できるのは ``id`` / ``speed`` / ``seed`` / ``lang``。
継続行は**区切り文字なしで連結**されるので、英語の台詞は 1 行に収めるか
行末に空白を置くこと（日本語では余計な空白が入らないようにこうしている）。
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .types import SynthesisRequest, TTSError

# 「話者: 台詞」。話者名には全角コロンも使えるようにする。
LINE_RE = re.compile(
    r"^(?P<voice>[^:：\[\]]+?)"  # 話者名
    r"(?:\[(?P<options>[^\]]*)\])?"  # 省略可能な [key=value, ...]
    r"\s*[:：]\s*"  # コロン（半角／全角）
    r"(?P<text>.*)$"
)

LINE_OPTION_KEYS = {"id", "speed", "seed", "lang"}
CAST_KEYS = {
    "engine",
    "reference_audio",
    "reference_text",
    "voice_design",
    "language",
    "seed",
    "speed",
}


class ScriptError(TTSError):
    """台本またはキャスト定義の書式が正しくない。"""


@dataclass(frozen=True)
class Voice:
    """cast.toml の 1 キャラクター。"""

    name: str
    engine: str
    reference_audio: Path | None = None
    reference_text: str | None = None
    voice_design: str | None = None
    language: str | None = None
    seed: int | None = None
    speed: float = 1.0


@dataclass(frozen=True)
class ScriptLine:
    """台本の 1 台詞。``index`` は台本中の並び順（1 始まり）。"""

    index: int
    voice: str
    text: str
    line_no: int  # エラーメッセージ用の台本内の行番号
    id: str | None = None
    language: str | None = None
    seed: int | None = None
    speed: float | None = None

    def output_name(self) -> str:
        """出力 wav のファイル名。並び順が一目で分かるよう連番を前に置く。"""
        if self.id:
            return f"{self.index:03d}-{self.id}.wav"
        return f"{self.index:03d}-{self.voice}.wav"


@dataclass
class Script:
    """台本全体。"""

    lines: list = field(default_factory=list)
    cast: dict = field(default_factory=dict)
    source: Path | None = None

    def voices_used(self) -> list:
        seen = []
        for line in self.lines:
            if line.voice not in seen:
                seen.append(line.voice)
        return seen

    def engines_used(self) -> list:
        seen = []
        for name in self.voices_used():
            engine = self.cast[name].engine
            if engine not in seen:
                seen.append(engine)
        return seen

    def to_request(self, line: ScriptLine, output_path: Path) -> SynthesisRequest:
        """1 台詞をキャラクターの声の設定と合成して SynthesisRequest にする。"""
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
        )


# --------------------------------------------------------------- cast.toml


def parse_cast(path: Path) -> dict:
    """cast.toml を読んで キャラクター名 -> Voice を返す。

    キャラクター名が日本語のときは TOML のテーブル名をクォートする必要がある::

        [voices."霊夢"]
        engine = "irodori"
        reference_audio = "voices/reimu.wav"
    """
    if not path.is_file():
        raise ScriptError(f"キャスト定義が見つかりません: {path}")

    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ScriptError(f"{path} を TOML として読めません: {exc}") from exc

    table = raw.get("voices")
    if not isinstance(table, dict) or not table:
        raise ScriptError(
            f'{path} に [voices."名前"] のセクションがありません。\n'
            '例:\n  [voices."霊夢"]\n  engine = "irodori"'
        )

    base_dir = path.parent
    cast: dict = {}
    for name, entry in table.items():
        if not isinstance(entry, dict):
            raise ScriptError(f'{path}: [voices."{name}"] はテーブルである必要があります。')

        unknown = set(entry) - CAST_KEYS
        if unknown:
            raise ScriptError(
                f'{path}: [voices."{name}"] に未知のキーがあります: {", ".join(sorted(unknown))}\n'
                f"使えるのは: {', '.join(sorted(CAST_KEYS))}"
            )
        if "engine" not in entry:
            raise ScriptError(f'{path}: [voices."{name}"] に engine がありません。')

        ref = entry.get("reference_audio")
        cast[name] = Voice(
            name=name,
            engine=str(entry["engine"]),
            # 参照音声は cast.toml からの相対パスで解決する。
            reference_audio=(base_dir / ref).resolve() if ref else None,
            reference_text=entry.get("reference_text"),
            voice_design=entry.get("voice_design"),
            language=entry.get("language"),
            seed=entry.get("seed"),
            speed=float(entry.get("speed", 1.0)),
        )
    return cast


# -------------------------------------------------------------- script.txt


def _parse_line_options(raw: str, line_no: int) -> dict:
    options: dict = {}
    for raw_chunk in raw.split(","):
        chunk = raw_chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ScriptError(
                f"{line_no} 行目: 角括弧の中は key=value で書いてください（'{chunk}'）。"
            )
        key, _, value = chunk.partition("=")
        key = key.strip()
        value = value.strip()
        if key not in LINE_OPTION_KEYS:
            raise ScriptError(
                f"{line_no} 行目: 未知のオプション '{key}'。"
                f" 使えるのは: {', '.join(sorted(LINE_OPTION_KEYS))}"
            )
        options[key] = value
    return options


def parse_script(path: Path, cast: dict) -> Script:
    """台本テキストを読み、キャスト定義と突き合わせて Script を返す。"""
    if not path.is_file():
        raise ScriptError(f"台本が見つかりません: {path}")

    lines: list = []
    pending: list = []  # 継続行を溜める場所

    def flush() -> None:
        if not pending:
            return
        head = pending[0]
        text = head["text"] + "".join(pending[1:])
        text = text.strip()
        if not text:
            raise ScriptError(f"{head['line_no']} 行目: 台詞が空です。")
        opts = head["options"]
        lines.append(
            ScriptLine(
                index=len(lines) + 1,
                voice=head["voice"],
                text=text,
                line_no=head["line_no"],
                id=opts.get("id"),
                language=opts.get("lang"),
                seed=int(opts["seed"]) if "seed" in opts else None,
                speed=float(opts["speed"]) if "speed" in opts else None,
            )
        )
        pending.clear()

    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()

        if stripped.startswith("#"):
            continue
        if not stripped:
            flush()
            continue

        # インデントされていて、直前に台詞があれば継続行として連結する。
        if pending and raw[:1] in (" ", "\t"):
            pending.append(stripped)
            continue

        match = LINE_RE.match(stripped)
        if match is None:
            raise ScriptError(
                f"{line_no} 行目を解釈できません: {stripped[:60]!r}\n"
                "「話者: 台詞」の形で書いてください。"
            )

        flush()
        voice = match.group("voice").strip()
        if voice not in cast:
            raise ScriptError(
                f"{line_no} 行目: キャスト定義に '{voice}' がありません。"
                f" 定義済み: {', '.join(cast)}"
            )
        pending.append(
            {
                "voice": voice,
                "text": match.group("text"),
                "line_no": line_no,
                "options": _parse_line_options(match.group("options") or "", line_no),
            }
        )

    flush()

    if not lines:
        raise ScriptError(f"{path} に台詞が 1 つもありません。")

    ids = [ln.id for ln in lines if ln.id]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ScriptError(f"id が重複しています: {', '.join(sorted(duplicates))}")

    return Script(lines=lines, cast=cast, source=path)


def load_script(cast_path: Path, script_path: Path) -> Script:
    return parse_script(script_path, parse_cast(cast_path))
