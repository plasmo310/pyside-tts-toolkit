"""Qwen3-TTS の runner。

    .venvs/engine-qwen/Scripts/python.exe -m ttstoolkit.engine.runners.qwen_runner

この仮想環境だけが qwen-tts / transformers 4.57.3 / torch cu128 を持つ。

Qwen3-TTS はチェックポイントが用途別に分かれている。

    Base        参照音声からのゼロショットクローン
    CustomVoice プリセット話者
    VoiceDesign 文章から架空の声を作る

リクエストの内容で使い分ける。全部を常にロードすると 12GB 級の VRAM を
圧迫するので、必要になった時点で初めてロードする。

torch とモデルのライブラリを関数の中で import しているのは、
`interface` より先に読み込まれて stdout の退避が間に合わなくなるのを
防ぐため (詳しくは `interface` の docstring を参照)。
"""

from __future__ import annotations

import time

from ttstoolkit.engine.runners.interface import (
    EngineRunner,
    log,
    serve,
    set_engine_name,
    write_wav_pcm16,
)

set_engine_name("qwen")

# 共通の言語コード -> Qwen が受け取る言語名
_LANGUAGE_NAMES = {"ja": "Japanese", "en": "English"}


class QwenRunner(EngineRunner):
    """Qwen3-TTS を常駐させる runner。

    Attributes:
        __options (dict): エンジン固有の設定。
        __device (str): 推論に使うデバイス。
        __models (dict): モデル識別子 -> ロード済みモデル。
    """

    def __init__(self, options: dict) -> None:
        """設定を読み取る（モデルはまだロードしない）。

        Args:
            options: エンジン固有の設定。
        """
        import torch

        self.__options = options
        self.__device = self.__resolve_device(
            str(options.get("device", "cuda:0"))
        )
        self.__dtype = {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }[str(options.get("dtype", "bfloat16"))]
        # flash_attention_2 は Windows でビルドが通らないため既定は sdpa
        self.__attn = str(options.get("attn_implementation", "sdpa"))
        self.__base_model = str(options.get("base_model", ""))
        self.__custom_model = str(options.get("custom_voice_model", ""))
        self.__design_model = str(options.get("voice_design_model", ""))
        self.__default_speaker = str(
            options.get("default_speaker", "ono_anna")
        )
        # 言語ごとの既定話者。Qwen のプリセットは言語色が強いので分ける
        self.__speakers = {
            str(key): str(value)
            for key, value in (options.get("speakers") or {}).items()
        }
        self.__max_new_tokens = int(options.get("max_new_tokens", 2048))
        self.__models: dict[str, object] = {}

        log(f"device={self.__device} attn={self.__attn}")
        log("Models are loaded on demand to save VRAM")

    @property
    def model_id(self) -> str:
        """既定で使うモデルの識別子。"""
        return self.__base_model

    def synthesize(self, message: dict) -> dict:
        """1 件を合成して wav を書き出す。

        Args:
            message: 親から届いたリクエスト。

        Returns:
            dict: サンプリングレート・長さ・所要時間・使ったモデル。

        Raises:
            ValueError: 声の指定の組み合わせが正しくないとき。
            RuntimeError: モデルが音声を返さなかったとき。
        """
        self.__apply_seed(message.get("seed"))

        language_code = message.get("language")
        language = (
            _LANGUAGE_NAMES.get(language_code) if language_code else None
        )
        reference = message.get("reference_audio")
        design = (message.get("voice_design") or "").strip()

        started = time.monotonic()
        if design:
            model_id, waves, sample_rate = self.__generate_design(
                message, language, design, reference
            )
        elif reference:
            model_id, waves, sample_rate = self.__generate_clone(
                message, language, reference
            )
        else:
            model_id, waves, sample_rate = self.__generate_preset(
                message, language, language_code
            )
        elapsed = time.monotonic() - started

        if not waves:
            raise RuntimeError("Qwen3-TTS returned no audio")

        frames = write_wav_pcm16(message["output_path"], waves[0], sample_rate)
        return {
            "sample_rate": int(sample_rate),
            "duration_sec": frames / int(sample_rate),
            "elapsed_sec": elapsed,
            "model_id": model_id,
        }

    def __generate_design(
        self,
        message: dict,
        language: str | None,
        design: str,
        reference: str | None,
    ) -> tuple[str, list, int]:
        """文章の指示から架空の声を作って読み上げる。

        Args:
            message: 親から届いたリクエスト。
            language: Qwen に渡す言語名。
            design: 声を説明する文章。
            reference: 参照音声のパス (指定されていたらエラーにする)。

        Returns:
            tuple[str, list, int]: モデル識別子・音声・サンプリングレート。

        Raises:
            ValueError: 参照音声と併用されたとき。
        """
        # 声の出どころがどちらか 1 つに決まらないので併用は禁じる
        if reference:
            raise ValueError(
                "Qwen3-TTS cannot combine voice design with a reference "
                "audio; drop one of them"
            )
        model = self.__load(self.__design_model)
        waves, sample_rate = model.generate_voice_design(
            text=message["text"],
            instruct=design,
            language=language,
            max_new_tokens=self.__max_new_tokens,
        )
        return self.__design_model, waves, sample_rate

    def __generate_clone(
        self, message: dict, language: str | None, reference: str
    ) -> tuple[str, list, int]:
        """参照音声の声を真似て読み上げる。

        Args:
            message: 親から届いたリクエスト。
            language: Qwen に渡す言語名。
            reference: 参照音声のパス。

        Returns:
            tuple[str, list, int]: モデル識別子・音声・サンプリングレート。
        """
        model = self.__load(self.__base_model)
        reference_text = message.get("reference_text")
        # 書き起こしが無いと ICL モードを使えない。話者埋め込みだけの
        # モードへ落とすが、クローン品質は下がるので警告を残す。
        x_vector_only = reference_text is None
        if x_vector_only:
            log(
                "No reference text given; falling back to "
                "x_vector_only_mode (cloning quality will be lower)"
            )
        waves, sample_rate = model.generate_voice_clone(
            text=message["text"],
            language=language,
            ref_audio=reference,
            ref_text=reference_text,
            x_vector_only_mode=x_vector_only,
            max_new_tokens=self.__max_new_tokens,
        )
        return self.__base_model, waves, sample_rate

    def __generate_preset(
        self, message: dict, language: str | None, language_code: str | None
    ) -> tuple[str, list, int]:
        """プリセット話者で読み上げる。

        Args:
            message: 親から届いたリクエスト。
            language: Qwen に渡す言語名。
            language_code: 共通の言語コード。話者を選ぶのに使う。

        Returns:
            tuple[str, list, int]: モデル識別子・音声・サンプリングレート。
        """
        model = self.__load(self.__custom_model)
        waves, sample_rate = model.generate_custom_voice(
            text=message["text"],
            speaker=self.__resolve_speaker(model, language_code),
            language=language,
            instruct=self.__options.get("instruct") or None,
            max_new_tokens=self.__max_new_tokens,
        )
        return self.__custom_model, waves, sample_rate

    def __load(self, model_id: str) -> object:
        """モデルをロードする (一度ロードしたものは使い回す)。

        Args:
            model_id: モデルの識別子。

        Returns:
            object: ロード済みモデル。
        """
        model = self.__models.get(model_id)
        if model is not None:
            return model

        from qwen_tts import Qwen3TTSModel

        log(f"Loading {model_id}")
        started = time.monotonic()
        model = Qwen3TTSModel.from_pretrained(
            model_id,
            device_map=self.__device,
            dtype=self.__dtype,
            attn_implementation=self.__attn,
        )
        self.__models[model_id] = model
        log(f"Loaded in {time.monotonic() - started:.1f}s")
        return model

    def __resolve_speaker(
        self, model: object, language_code: str | None
    ) -> str:
        """使うプリセット話者を決める。

        Args:
            model: ロード済みの CustomVoice モデル。
            language_code: 共通の言語コード。

        Returns:
            str: 話者 ID。

        Raises:
            ValueError: モデルが持たない話者を指定したとき。
        """
        wanted = self.__speakers.get(
            language_code or "", self.__default_speaker
        )
        speakers = model.get_supported_speakers() or []
        if not speakers:
            return wanted
        # 話者 ID は小文字。設定で大文字始まりを書いても通るようにする
        lookup = {speaker.lower(): speaker for speaker in speakers}
        if wanted.lower() in lookup:
            return lookup[wanted.lower()]
        raise ValueError(
            f"Speaker {wanted!r} is not in this model; choose one of: "
            f"{', '.join(speakers)}"
        )

    @staticmethod
    def __resolve_device(requested: str) -> str:
        """使えるデバイスを決める。

        Args:
            requested: 設定で指定されたデバイス。

        Returns:
            str: 実際に使うデバイス。
        """
        import torch

        if requested.startswith("cuda") and not torch.cuda.is_available():
            log("CUDA is not available; falling back to CPU (much slower)")
            return "cpu"
        return requested

    @staticmethod
    def __apply_seed(seed: int | None) -> None:
        """乱数シードを固定する。

        生成はサンプリングを含むため、再現性はグローバルシードで担保する。

        Args:
            seed: 乱数シード。None なら何もしない。
        """
        if seed is None:
            return

        import torch

        torch.manual_seed(int(seed))
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(int(seed))


if __name__ == "__main__":
    raise SystemExit(serve(QwenRunner))
