"""Irodori-TTS v4.1 Small の runner。

    .venvs/engine-irodori/Scripts/python.exe \
        -m ttstoolkit.engine.irodori.runner

Irodori は PyPI 未公開 (依存の dacvae も PyPI に無い) ため、上流
リポジトリを `engine_env/irodori/vendor/Irodori-TTS` へ clone し、その
リポジトリ自身の仮想環境を使う。clone は非パッケージ扱いで仮想環境には
入らないので、`core.engine` が clone の場所を検索パス
(`EngineSpec.python_path`) に足している。

付属の infer.py を毎回叩くとリクエストごとにモデルをロードし直すので、
内部 API (`InferenceRuntime`) を直接使って常駐させる。

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

set_engine_name("irodori")


class IrodoriRunner(EngineRunner):
    """Irodori-TTS を常駐させる runner。

    Attributes:
        __options (dict): エンジン固有の設定。
        __checkpoint_repo (str): 使うチェックポイントの Hugging Face ID。
        __runtime (object): ロード済みの InferenceRuntime。
    """

    def __init__(self, options: dict) -> None:
        """チェックポイントを取得してモデルをロードする。

        Args:
            options: エンジン固有の設定。
        """
        from irodori_tts.inference_runtime import (
            InferenceRuntime,
            RuntimeKey,
            default_runtime_device,
            download_hf_checkpoint,
        )

        self.__options = options
        self.__checkpoint_repo = str(options.get("hf_checkpoint", ""))
        device = self.__resolve_device(
            str(options.get("device") or default_runtime_device())
        )

        log(f"Fetching checkpoint {self.__checkpoint_repo}")
        checkpoint_path = download_hf_checkpoint(self.__checkpoint_repo)

        log(f"Loading the model (device={device})")
        started = time.monotonic()
        self.__runtime = InferenceRuntime.from_key(
            RuntimeKey(
                checkpoint=str(checkpoint_path),
                model_device=device,
                codec_repo=str(options.get("codec_repo", "")),
                model_precision=str(options.get("model_precision", "fp32")),
                codec_device=str(options.get("codec_device", "cpu")),
                codec_precision=str(options.get("codec_precision", "fp32")),
            )
        )
        log(f"Loaded in {time.monotonic() - started:.1f}s")

    @property
    def model_id(self) -> str:
        """ロードしたモデルの識別子。"""
        return self.__checkpoint_repo

    def synthesize(self, request: SynthesisRequest) -> SynthesisResponse:
        """1 件を合成して wav を書き出す。

        Args:
            request: 親から届いたリクエスト。

        Returns:
            SynthesisResponse: サンプリングレート・長さ・所要時間。

        Raises:
            ValueError: 日本語以外が指定されたとき。
        """
        from irodori_tts.inference_runtime import SamplingRequest

        if request.language not in (None, "ja"):
            raise ValueError(
                f"Irodori-TTS is Japanese only (got {request.language!r})"
            )

        reference = request.reference_audio
        caption = self.__resolve_caption(request)
        cfg_text, cfg_caption, cfg_speaker = self.__resolve_cfg(
            caption, reference
        )

        # 共通の speed は「速いほど短い」。Irodori の duration_scale は
        # 「大きいほど長い」ので逆数を渡す。
        num_steps = self.__options.get("num_steps")

        sampling = SamplingRequest(
            text=request.text,
            caption=caption,
            ref_wav=reference,
            no_ref=reference is None,
            seed=request.seed,
            duration_scale=1.0 / request.speed,
            num_steps=int(num_steps) if num_steps else None,
            cfg_scale_text=cfg_text,
            cfg_scale_caption=cfg_caption,
            cfg_scale_speaker=cfg_speaker,
            cfg_guidance_mode=self.__guidance_mode(),
        )

        started = time.monotonic()
        result = self.__runtime.synthesize(sampling, log_fn=log)
        elapsed = time.monotonic() - started

        for line in result.messages or []:
            log(line)

        sample_rate = int(result.sample_rate)
        frames = write_wav_pcm16(
            request.output_path, result.audio, sample_rate
        )
        return SynthesisResponse(
            sample_rate=sample_rate,
            duration_sec=frames / sample_rate,
            elapsed_sec=elapsed,
        )

    def __resolve_caption(self, request: SynthesisRequest) -> str | None:
        """声と話し方を説明する文章 (caption) を決める。

        Irodori では参照音声と併用でき、その場合は声質が参照音声、
        話し方が caption になる。

        Args:
            request: 親から届いたリクエスト。

        Returns:
            str | None: caption。指定が無ければ None。
        """
        caption = request.voice_design or self.__options.get("caption") or ""
        return str(caption).strip() or None

    def __resolve_cfg(
        self, caption: str | None, reference: str | None
    ) -> tuple[float, float, float]:
        """CFG スケールを上流の作法どおりに整える。

        Args:
            caption: 声を説明する文章。
            reference: 参照音声のパス。

        Returns:
            tuple[float, float, float]: text / caption / speaker の
                それぞれのスケール。
        """
        from irodori_tts.inference_runtime import resolve_cfg_scales

        model_cfg = self.__runtime.model_cfg
        cfg_text, cfg_caption, cfg_speaker, messages = resolve_cfg_scales(
            cfg_guidance_mode=self.__guidance_mode(),
            cfg_scale_text=float(self.__options.get("cfg_scale_text", 3.0)),
            cfg_scale_caption=float(
                self.__options.get("cfg_scale_caption", 3.0)
            ),
            cfg_scale_speaker=float(
                self.__options.get("cfg_scale_speaker", 5.0)
            ),
            cfg_scale=None,
            use_caption_condition=bool(
                model_cfg.use_caption_condition and caption
            ),
            use_speaker_condition=bool(
                model_cfg.use_speaker_condition_resolved and reference
            ),
        )
        for line in messages:
            log(line)
        return cfg_text, cfg_caption, cfg_speaker

    def __guidance_mode(self) -> str:
        """CFG のガイダンスモードを返す。"""
        return str(self.__options.get("cfg_guidance_mode", "independent"))

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


if __name__ == "__main__":
    raise SystemExit(serve(IrodoriRunner))
