"""エンジンとは何か ── 定義・対応機能・名前からの引き当て。

「どのモデルをどの仮想環境で動かすか」の定義 (`ENGINE_DEFINITIONS`) と、
それを扱うための型をここに集める。定義を持っているのがここなので、
名前からの引き当て (`get_spec` など) もここに置く。

呼ばれる先: cli/, gui/, core.tts_service, core._internal.engine_process
呼ぶ先: core.settings, core.paths

実際に動くエンジンを作るのは `core._internal.engine_process.create_engine`。
このモジュールは torch を含むモデル依存を一切持たない。GUI からも CLI
からも、外部ツールとの連携コードからもそのまま import できる。

runner とやり取りする型 (`SynthesisRequest` / `SynthesisResponse`) は
両側が守る契約なので `ttstoolkit.engine._shared.protocol` にある。

3 モデルは transformers / torch のピンが互いに排他的で、1 つの仮想環境には
同居できない。エンジンごとに仮想環境を持ち、共通層はサブプロセス越しに
runner を呼ぶ。

    qwen       : transformers==4.57.3
    chatterbox : transformers==5.2.0, torch==2.6.0 (Blackwell 対応で上書き)
    irodori    : transformers>=5.12.1, torch>=2.10

仮想環境の定義は engine_env/<name>/pyproject.toml、実体は .venvs/engine-*。
構築手順は scripts/win/setup_engines.ps1 を参照。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum, Flag, auto

from ttstoolkit.core.paths import PYTHON_DIR, ROOT_DIR, venv_python
from ttstoolkit.core.settings import TTSToolkitError

# Irodori は PyPI 未公開で、依存の dacvae も PyPI に無い。上流リポジトリを
# clone したものを検索パスに足して import する。
_IRODORI_VENDOR = os.path.join(
    ROOT_DIR, "engine_env", "irodori", "vendor", "Irodori-TTS"
)


class EngineType(Enum):
    """エンジンの選択肢。値は `ENGINE_DEFINITIONS` のキー。"""

    QWEN = "qwen"
    CHATTERBOX = "chatterbox"
    IRODORI = "irodori"

    @classmethod
    def from_name(cls, name: str) -> EngineType | None:
        """エンジン名から種別を返却する。該当が無ければ None。"""
        for member in cls:
            if member.value == name:
                return member
        return None


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
    """1 つのエンジンの定義。実体は `ENGINE_DEFINITIONS`。

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

    @property
    def setup_doc_path(self) -> str:
        """セットアップ手順の `docs/setup/` から始まるパスを返す。"""
        return f"docs/setup/{self.setup_doc}"


ENGINE_DEFINITIONS: dict[str, EngineSpec] = {
    EngineType.QWEN.value: EngineSpec(
        name=EngineType.QWEN.value,
        description=(
            "Qwen3-TTS 1.7B - high quality in both Japanese and English; "
            "3-second cloning and voice design"
        ),
        capabilities=(
            Capability.CLONE
            | Capability.SEED
            | Capability.MULTILINGUAL
            | Capability.VOICE_DESIGN
        ),
        languages=("ja", "en"),
        model_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        python=venv_python("engine-qwen"),
        runner="ttstoolkit.engine.qwen.runner",
        cwd=ROOT_DIR,
        setup_doc="01_qwen3-tts.md",
        python_path=(PYTHON_DIR,),
        options={
            # 参照音声ありのときに使うクローンモデル。
            # VRAM が足りなければ 0.6B に下げる。
            "base_model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
            # 参照音声なしのときに使うプリセット話者モデル。
            "custom_voice_model": ("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"),
            # 文章から架空の声を作るときに使うモデル。
            "voice_design_model": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            # CustomVoice が持つ話者は aiden, dylan, eric, ono_anna,
            # ryan, serena, sohee, uncle_fu, vivian の 9 名。
            "default_speaker": "ono_anna",
            "speakers": {"ja": "ono_anna", "en": "ryan"},
            "dtype": "bfloat16",
            "device": "cuda:0",
            # flash_attention_2 は Windows でビルドが通らないため sdpa。
            "attn_implementation": "sdpa",
            "max_new_tokens": 2048,
        },
    ),
    EngineType.CHATTERBOX.value: EngineSpec(
        name=EngineType.CHATTERBOX.value,
        description=(
            "Chatterbox Multilingual V3 - 0.5B, 23 languages, "
            "the lightest to set up"
        ),
        capabilities=(
            Capability.CLONE | Capability.SEED | Capability.MULTILINGUAL
        ),
        languages=("ja", "en"),
        model_id="ResembleAI/chatterbox (multilingual v3)",
        python=venv_python("engine-chatterbox"),
        runner="ttstoolkit.engine.chatterbox.runner",
        cwd=ROOT_DIR,
        setup_doc="02_chatterbox.md",
        python_path=(PYTHON_DIR,),
        options={
            "t3_model": "v3",
            "device": "cuda",
            "exaggeration": 0.5,
            "cfg_weight": 0.5,
            "temperature": 0.8,
        },
    ),
    EngineType.IRODORI.value: EngineSpec(
        name=EngineType.IRODORI.value,
        description=(
            "Irodori-TTS v4.1 Small - Japanese only, 48 kHz, "
            "strong at voice design and emotion"
        ),
        capabilities=(
            Capability.CLONE
            | Capability.SEED
            | Capability.SPEED
            | Capability.VOICE_DESIGN
        ),
        languages=("ja",),
        model_id="Aratako/Irodori-TTS-v4.1-Small",
        python=venv_python("engine-irodori"),
        runner="ttstoolkit.engine.irodori.runner",
        # 上流リポジトリは相対パスで作業ファイルを置くので clone の中で動かす。
        cwd=_IRODORI_VENDOR,
        setup_doc="03_irodori-tts.md",
        python_path=(PYTHON_DIR, _IRODORI_VENDOR),
        options={
            "hf_checkpoint": "Aratako/Irodori-TTS-v4.1-Small",
            "codec_repo": "Aratako/Semantic-DACVAE-Japanese-32dim",
            "model_precision": "fp32",
            "num_steps": 24,
            "cfg_guidance_mode": "independent",
            "cfg_scale_text": 3.0,
            "cfg_scale_caption": 3.0,
            "cfg_scale_speaker": 5.0,
        },
    ),
}


def engine_names() -> list[str]:
    """使えるエンジン名を定義順で返す。"""
    return list(ENGINE_DEFINITIONS)


def available_engines() -> dict[str, EngineSpec]:
    """エンジン名 -> 定義の辞書を返す。"""
    return dict(ENGINE_DEFINITIONS)


def get_spec(name: str) -> EngineSpec:
    """エンジン名から定義を返す。

    Args:
        name: エンジン名。

    Returns:
        EngineSpec: そのエンジンの定義。

    Raises:
        EngineNotFoundError: 定義されていない名前のとき。
    """
    spec = ENGINE_DEFINITIONS.get(name)
    if spec is None:
        raise EngineNotFoundError(
            f"Unknown engine '{name}' (available: {', '.join(engine_names())})"
        )
    return spec
