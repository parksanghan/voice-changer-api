from typing import Any
import torch
import torch.nn.functional as F
from torch.cuda.amp import autocast
from Exceptions import (
    DeviceCannotSupportHalfPrecisionException,
    DeviceChangingException,
    HalfPrecisionChangingException,
    NotEnoughDataExtimateF0,
)
from mods.log_control import VoiceChangaerLogger
from voice_changer.DiffusionSVC.inferencer.Inferencer import Inferencer
from voice_changer.DiffusionSVC.pitchExtractor.PitchExtractor import PitchExtractor

from voice_changer.RVC.embedder.Embedder import Embedder

from voice_changer.common.VolumeExtractor import VolumeExtractor
from torchaudio.transforms import Resample

from voice_changer.utils.Timer import Timer2

logger = VoiceChangaerLogger.get_instance().getLogger()


class Pipeline(object):
    embedder: Embedder
    inferencer: Inferencer
    pitchExtractor: PitchExtractor

    index: Any | None
    big_npy: Any | None
    # feature: Any | None

    targetSR: int
    device: torch.device
    isHalf: bool

    def __init__(
        self,
        embedder: Embedder,
        inferencer: Inferencer,
        pitchExtractor: PitchExtractor,
        # index: Any | None,
        targetSR,
        device,
        isHalf,
        resamplerIn: Resample,
        resamplerOut: Resample,
    ):
        self.inferencer = inferencer
        inferencer_block_size, inferencer_sampling_rate = inferencer.getConfig()
        self.hop_size = inferencer_block_size * 16000 / inferencer_sampling_rate  # 16000はオーディオのサンプルレート。16Kで処理
        self.inferencer_block_size = inferencer_block_size
        self.inferencer_sampling_rate = inferencer_sampling_rate

        self.volumeExtractor = VolumeExtractor(self.hop_size)
        self.embedder = embedder
        self.pitchExtractor = pitchExtractor

        self.resamplerIn = resamplerIn
        self.resamplerOut = resamplerOut

        logger.info("VOLUME EXTRACTOR" + str(self.volumeExtractor))
        logger.info("GENERATE INFERENCER" + str(self.inferencer))
        logger.info("GENERATE EMBEDDER" + str(self.embedder))
        logger.info("GENERATE PITCH EXTRACTOR" + str(self.pitchExtractor))

        self.targetSR = targetSR
        self.device = device
        self.isHalf = False

    def getPipelineInfo(self):
        volumeExtractorInfo = self.volumeExtractor.getVolumeExtractorInfo()
        inferencerInfo = self.inferencer.getInferencerInfo() if self.inferencer else {}
        embedderInfo = self.embedder.getEmbedderInfo()
        pitchExtractorInfo = self.pitchExtractor.getPitchExtractorInfo()
        return {"volumeExtractor": volumeExtractorInfo, "inferencer": inferencerInfo, "embedder": embedderInfo, "pitchExtractor": pitchExtractorInfo, "isHalf": self.isHalf}

    def setPitchExtractor(self, pitchExtractor: PitchExtractor):
        self.pitchExtractor = pitchExtractor

    @torch.no_grad()
    def extract_volume_and_mask(self, audio: torch.Tensor, threshold: float):
        volume_t = self.volumeExtractor.extract_t(audio)
        mask = self.volumeExtractor.get_mask_from_volume_t(volume_t, self.inferencer_block_size, threshold=threshold)
        volume = volume_t.unsqueeze(-1).unsqueeze(0)
        return volume, mask

    def exec(
        self,
        sid,
        audio,  # torch.tensor [n]
        sr,
        pitchf,  # np.array [m]
        feature,  # np.array [m, feat]
        f0_up_key,
        k_step,
        infer_speedup,
        silence_front,
        embOutputLayer,
        useFinalProj,
        protect=0.5,
        skip_diffusion=True,
    ):
        # print("---------- pipe line --------------------")
        with Timer2("pre-process", False) as t:
            audio_t = torch.from_numpy(audio).float().unsqueeze(0).to(self.device)
            audio16k = self.resamplerIn(audio_t)
            volume, mask = self.extract_volume_and_mask(audio16k, threshold=-60.0)
            sid = torch.tensor(sid, device=self.device).unsqueeze(0).long()
            n_frames = int(audio16k.size(-1) // self.hop_size + 1)
        # print("[Timer::1: ]", t.secs)

        with Timer2("pre-process", False) as t:
            # ピッチ検出
            try:
                # pitch = self.pitchExtractor.extract(
                #     audio16k.squeeze(),
                #     pitchf,
                #     f0_up_key,
                #     int(self.hop_size),    # 処理のwindowサイズ (44100における512)
                #     silence_front=silence_front,
                # )
                pitch = self.pitchExtractor.extract(
                    audio,
                    sr,
                    self.inferencer_block_size,
                    self.inferencer_sampling_rate,
                    pitchf,
                    f0_up_key,
                    silence_front=silence_front,
                )
                pitch = torch.tensor(pitch[-n_frames:], device=self.device, dtype=torch.float).unsqueeze(0).long()
            except IndexError as e:  # NOQA
                raise NotEnoughDataExtimateF0()

            # tensor型調整
            feats = audio16k.squeeze()
            if feats.dim() == 2:  # double channels
                feats = feats.mean(-1)
            feats = feats.view(1, -1)
        # print("[Timer::2: ]", t.secs)

        with Timer2("pre-process", False) as t:
            # embedding
            with autocast(enabled=self.isHalf):
                try:
                    feats = self.embedder.extractFeatures(feats, embOutputLayer, useFinalProj)
                    if torch.isnan(feats).all():
                        raise DeviceCannotSupportHalfPrecisionException()
                except RuntimeError as e:
                    if "HALF" in e.__str__().upper():
                        raise HalfPrecisionChangingException()
                    elif "same device" in e.__str__():
                        raise DeviceChangingException()
                    else:
                        raise e
            feats = F.interpolate(feats.permute(0, 2, 1), size=int(n_frames), mode="nearest").permute(0, 2, 1)
        # print("[Timer::3: ]", t.secs)

        with Timer2("pre-process", False) as t:
            # 推論実行
            try:
                with torch.no_grad():
                    with autocast(enabled=self.isHalf):
                        audio1 = (
                            torch.clip(
                                self.inferencer.infer(audio16k, feats, pitch.unsqueeze(-1), volume, mask, sid, k_step, infer_speedup, silence_front=silence_front, skip_diffusion=skip_diffusion).to(dtype=torch.float32),
                                -1.0,
                                1.0,
                            )
                            * 32767.5
                        ).data.to(dtype=torch.int16)
            except RuntimeError as e:
                if "HALF" in e.__str__().upper():
                    print("11", e)
                    raise HalfPrecisionChangingException()
                else:
                    raise e
        # print("[Timer::4: ]", t.secs)

        with Timer2("pre-process", False) as t:  # NOQA
            feats_buffer = feats.squeeze(0).detach().cpu()
            if pitch is not None:
                pitch_buffer = pitch.squeeze(0).detach().cpu()
            else:
                pitch_buffer = None

            del pitch, pitchf, feats, sid
            audio1 = self.resamplerOut(audio1.float())
        # print("[Timer::5: ]", t.secs)
        return audio1, pitch_buffer, feats_buffer
