"""エンジンを扱うためのデータクラスと、エンジン固有のエラー。

親プロセス側だけが使う型を置く。runner とやり取りする型
(`SynthesisRequest` / `SynthesisResponse`) は両側が守る契約なので
`ttstoolkit.engine._shared.protocol` にある。

このモジュールは torch を含むモデル依存を一切持たない。GUI からも CLI
からも、外部ツールとの連携コードからもそのまま import できる。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from enum import Flag, auto

from ttstoolkit.core.settings import TTSToolkitError


class Capability(Flag):
    """エンジンが対応している機能。

    未対応のパラメータを黙って無視すると「指定したのに効いていない」と
    いう最も気づきにくい不具合になるため、対応状況をここで宣言して
    `TTSEngine.validate()` が起動前に弾けるようにしている。
    """

    NONE = 0
    CLONE = auto()  # 参照音声によるゼロショットクローン
    SPEED = auto()  # 話速指定
    SEED = auto()  # 乱数シード固定
    MULTILINGUAL = auto()  # 日本語以外も生成できる
    VOICE_DESIGN = auto()  # 文章の指示から声そのものを設計する


class EngineNotFoundError(TTSToolkitError):
    """定義されていないエンジン名が指定された。"""


class EngineNotInstalledError(TTSToolkitError):
    """エンジンの仮想環境がまだ構築されていない。"""


class UnsupportedParameterError(TTSToolkitError):
    """エンジンが対応していないパラメータが既定値以外で渡された。"""


class UnsupportedLanguageError(TTSToolkitError):
    """エンジンが対応していない言語が指定された。"""


class EngineProcessError(TTSToolkitError):
    """runner プロセスの起動・通信・合成が失敗した。"""


@dataclass(frozen=True)
class SynthesisResult:
    """1 件の合成結果。呼び出し側 (CLI / GUI) に返す形。

    runner が返す `SynthesisResponse` に、親が知っている書き出し先と
    エンジン名を足したもの。

    Attributes:
        output_path: 書き出した wav のパス。
        sample_rate: サンプリングレート (Hz)。
        duration_sec: 音声の長さ (秒)。
        engine: 使ったエンジン名。
        model_id: 実際に使ったモデルの識別子。
        elapsed_sec: 合成にかかった時間 (秒)。
    """

    output_path: str
    sample_rate: int
    duration_sec: float
    engine: str
    model_id: str
    elapsed_sec: float

    def to_dict(self) -> dict[str, object]:
        """manifest に書き出すための辞書を返す。"""
        return {
            "output_path": self.output_path,
            "sample_rate": self.sample_rate,
            "duration_sec": round(self.duration_sec, 3),
            "engine": self.engine,
            "model_id": self.model_id,
            "elapsed_sec": round(self.elapsed_sec, 3),
        }


@dataclass(frozen=True)
class EngineSpec:
    """1 つのエンジンの定義。実体は `tool_config.ENGINE_DEFINITIONS`。

    Attributes:
        name: エンジン名 (`qwen` など)。
        description: 一覧に出す説明。
        capabilities: 対応している機能。
        languages: 対応している言語コード。
        model_id: 既定で使うモデルの識別子。
        python: このエンジンの仮想環境の python 実行ファイル。
        runner: runner モジュール名 (`-m` に渡す)。
        cwd: runner を起動する作業ディレクトリ。
        setup_doc: `docs/setup/` 配下の該当ファイル名。
        options: runner へそのまま渡すエンジン固有の設定。
        python_path: runner の検索パスに足すディレクトリ。
    """

    name: str
    description: str
    capabilities: Capability
    languages: tuple[str, ...]
    model_id: str
    python: str
    runner: str
    cwd: str
    setup_doc: str
    options: dict = field(default_factory=dict)
    python_path: tuple[str, ...] = ()

    def supports(self, capability: Capability) -> bool:
        """機能に対応しているかを返す。

        Args:
            capability: 調べる機能。

        Returns:
            bool: 対応していれば True。
        """
        return bool(self.capabilities & capability)

    @property
    def installed(self) -> bool:
        """仮想環境が構築済みかを返す。"""
        return os.path.isfile(self.python)


def default_output_path(engine: str, text: str, output_dir: str) -> str:
    """テキストから決まるファイル名を作る (再生成時の取り違え防止)。

    Args:
        engine: エンジン名。
        text: 読み上げるテキスト。
        output_dir: 書き出し先ディレクトリ。

    Returns:
        str: 書き出す wav のパス。
    """
    digest = hashlib.sha256(f"{engine}\n{text}".encode()).hexdigest()[:12]
    return os.path.join(output_dir, f"{engine}-{digest}.wav")
