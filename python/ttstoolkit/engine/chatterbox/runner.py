"""Chatterbox Multilingual V3 の runner。

    .venvs/engine-chatterbox/Scripts/python.exe \
        -m ttstoolkit.engine.chatterbox.runner

この仮想環境だけが chatterbox-tts / transformers 5.2.0 /
torch 2.7.1+cu128 を持つ。3 つのエンジンの中では最も軽く、導入も速い。

torch とモデルのライブラリを関数の中で import しているのは、
`runner_base` より先に読み込まれて stdout の退避が間に合わなくなるのを
防ぐため (詳しくは `_shared/runner_base.py` の docstring を参照)。
"""

from __future__ import annotations

import time

from ttstoolkit.engine._shared.protocol import (
    SynthesisRequest,
    SynthesisResponse,
)
from ttstoolkit.engine._shared.runner_base import (
    EngineRunner,
    log,
    serve,
    set_engine_name,
    write_wav_pcm16,
)

set_engine_name("chatterbox")


class ChatterboxRunner(EngineRunner):
    """Chatterbox Multilingual を常駐させる runner。

    Attributes:
        __options (dict): エンジン固有の設定。
        __t3_model (str): 使うチェックポイントの世代。
        __model (object): ロード済みモデル。
    """

    def __init__(self, options: dict) -> None:
        """モデルをロードする。

        Args:
            options: エンジン固有の設定。
        """
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        self.__options = options
        self.__t3_model = str(options.get("t3_model") or "v3")
        device = self.__resolve_device(str(options.get("device", "cuda")))

        log(f"device={device} t3_model={self.__t3_model}")
        started = time.monotonic()
        self.__model = ChatterboxMultilingualTTS.from_pretrained(
            device=device, t3_model=self.__t3_model
        )
        log(f"Loaded in {time.monotonic() - started:.1f}s")

    @property
    def model_id(self) -> str:
        """ロードしたモデルの識別子。"""
        return f"ResembleAI/chatterbox multilingual {self.__t3_model}"

    def synthesize(self, request: SynthesisRequest) -> SynthesisResponse:
        """1 件を合成して wav を書き出す。

        Args:
            request: 親から届いたリクエスト。

        Returns:
            SynthesisResponse: サンプリングレート・長さ・所要時間。

        Raises:
            ValueError: 対応していない言語が指定されたとき。
        """
        from chatterbox.mtl_tts import SUPPORTED_LANGUAGES

        language = request.language or "ja"
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Chatterbox does not support language {language!r} "
                f"(supported: {', '.join(sorted(SUPPORTED_LANGUAGES))})"
            )

        self.__apply_seed(request.seed)

        started = time.monotonic()
        wave_data = self.__model.generate(
            request.text,
            language_id=language,
            audio_prompt_path=request.reference_audio,
            exaggeration=float(self.__options.get("exaggeration", 0.5)),
            cfg_weight=float(self.__options.get("cfg_weight", 0.5)),
            temperature=float(self.__options.get("temperature", 0.8)),
        )
        elapsed = time.monotonic() - started

        sample_rate = int(self.__model.sr)
        frames = write_wav_pcm16(request.output_path, wave_data, sample_rate)
        return SynthesisResponse(
            sample_rate=sample_rate,
            duration_sec=frames / sample_rate,
            elapsed_sec=elapsed,
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
    raise SystemExit(serve(ChatterboxRunner))
