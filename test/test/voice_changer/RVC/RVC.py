from dataclasses import asdict
import numpy as np
import torch
import torchaudio
from data.ModelSlot import RVCModelSlot
from mods.log_control import VoiceChangaerLogger

from voice_changer.RVC.RVCSettings import RVCSettings
from voice_changer.RVC.embedder.EmbedderManager import EmbedderManager
from voice_changer.utils.VoiceChangerModel import AudioInOut, PitchfInOut, FeatureInOut, VoiceChangerModel
from voice_changer.utils.VoiceChangerParams import VoiceChangerParams
from voice_changer.RVC.onnxExporter.export2onnx import export2onnx
from voice_changer.RVC.pitchExtractor.PitchExtractorManager import PitchExtractorManager
from voice_changer.RVC.pipeline.PipelineGenerator import createPipeline
from voice_changer.RVC.deviceManager.DeviceManager import DeviceManager
from voice_changer.RVC.pipeline.Pipeline import Pipeline

from Exceptions import DeviceCannotSupportHalfPrecisionException, PipelineCreateException, PipelineNotInitializedException

logger = VoiceChangaerLogger.get_instance().getLogger()


class RVC(VoiceChangerModel):
    def __init__(self, params: VoiceChangerParams, slotInfo: RVCModelSlot):
        logger.info("[Voice Changer] [RVC] Creating instance ")
        self.deviceManager = DeviceManager.get_instance()
        EmbedderManager.initialize(params)
        PitchExtractorManager.initialize(params)
        self.settings = RVCSettings()
        self.params = params
        # self.pitchExtractor = PitchExtractorManager.getPitchExtractor(self.settings.f0Detector, self.settings.gpu)

        self.pipeline: Pipeline | None = None

        self.audio_buffer: AudioInOut | None = None
        self.pitchf_buffer: PitchfInOut | None = None
        self.feature_buffer: FeatureInOut | None = None
        self.prevVol = 0.0
        self.slotInfo = slotInfo
        # self.initialize()

    def initialize(self):
        logger.info("[Voice Changer][RVC] Initializing... ")

        # pipelineの生成
        try:
            self.pipeline = createPipeline(self.slotInfo, self.settings.gpu, self.settings.f0Detector)
        except PipelineCreateException as e:  # NOQA
            logger.error("[Voice Changer] pipeline create failed. check your model is valid.")
            return

        # その他の設定
        self.settings.tran = self.slotInfo.defaultTune
        self.settings.indexRatio = self.slotInfo.defaultIndexRatio
        self.settings.protect = self.slotInfo.defaultProtect
        logger.info("[Voice Changer] [RVC] Initializing... done")

    def update_settings(self, key: str, val: int | float | str):
        logger.info(f"[Voice Changer][RVC]: update_settings {key}:{val}")
        if key in self.settings.intData:
            setattr(self.settings, key, int(val))
            if key == "gpu":
                self.deviceManager.setForceTensor(False)
                self.initialize()
        elif key in self.settings.floatData:
            setattr(self.settings, key, float(val))
        elif key in self.settings.strData:
            setattr(self.settings, key, str(val))
            if key == "f0Detector" and self.pipeline is not None:
                pitchExtractor = PitchExtractorManager.getPitchExtractor(self.settings.f0Detector, self.settings.gpu)
                self.pipeline.setPitchExtractor(pitchExtractor)
        else:
            return False
        return True

    def get_info(self):
        data = asdict(self.settings)
        if self.pipeline is not None:
            pipelineInfo = self.pipeline.getPipelineInfo()
            data["pipelineInfo"] = pipelineInfo
        else:
            data["pipelineInfo"] = "None"
        return data

    def get_processing_sampling_rate(self):
        return self.slotInfo.samplingRate

    def generate_input(
        self,
        newData: AudioInOut,
        inputSize: int,
        crossfadeSize: int,
        solaSearchFrame: int = 0,
    ):
        newData = newData.astype(np.float32) / 32768.0  # RVCのモデルのサンプリングレートで入ってきている。（extraDataLength, Crossfade等も同じSRで処理）(★１)
        # ↑newData.shape[0]//sampleRate でデータ秒数。これに16000かけてhubertの世界でのデータ長。これにhop数(160)でわるとfeatsのデータサイズになる。
        new_feature_length = newData.shape[0] * 100 // self.slotInfo.samplingRate
        if self.audio_buffer is not None:
            # 過去のデータに連結
            self.audio_buffer = np.concatenate([self.audio_buffer, newData], 0)
            if self.slotInfo.f0:
                self.pitchf_buffer = np.concatenate([self.pitchf_buffer, np.zeros(new_feature_length)], 0)
            self.feature_buffer = np.concatenate([self.feature_buffer, np.zeros([new_feature_length, self.slotInfo.embChannels])], 0)
        else:
            self.audio_buffer = newData
            if self.slotInfo.f0:
                self.pitchf_buffer = np.zeros(new_feature_length)
            self.feature_buffer = np.zeros([new_feature_length, self.slotInfo.embChannels])

        convertSize = inputSize + crossfadeSize + solaSearchFrame + self.settings.extraConvertSize

        if convertSize % 128 != 0:  # モデルの出力のホップサイズで切り捨てが発生するので補う。
            convertSize = convertSize + (128 - (convertSize % 128))
        outSize = convertSize - self.settings.extraConvertSize

        # バッファがたまっていない場合はzeroで補う
        if self.audio_buffer.shape[0] < convertSize:
            self.audio_buffer = np.concatenate([np.zeros([convertSize]), self.audio_buffer])
            if self.slotInfo.f0:
                self.pitchf_buffer = np.concatenate([np.zeros([convertSize * 100 // self.slotInfo.samplingRate]), self.pitchf_buffer])
            self.feature_buffer = np.concatenate([np.zeros([convertSize * 100 // self.slotInfo.samplingRate, self.slotInfo.embChannels]), self.feature_buffer])

        convertOffset = -1 * convertSize
        featureOffset = -convertSize * 100 // self.slotInfo.samplingRate
        self.audio_buffer = self.audio_buffer[convertOffset:]  # 変換対象の部分だけ抽出
        if self.slotInfo.f0:
            self.pitchf_buffer = self.pitchf_buffer[featureOffset:]
        self.feature_buffer = self.feature_buffer[featureOffset:]

        # 出力部分だけ切り出して音量を確認。(TODO:段階的消音にする)
        cropOffset = -1 * (inputSize + crossfadeSize)
        cropEnd = -1 * (crossfadeSize)
        crop = self.audio_buffer[cropOffset:cropEnd]
        vol = np.sqrt(np.square(crop).mean())
        vol = max(vol, self.prevVol * 0.0)
        self.prevVol = vol

        return (self.audio_buffer, self.pitchf_buffer, self.feature_buffer, convertSize, vol, outSize)

    def inference(self, data):
        if self.pipeline is None:
            logger.info("[Voice Changer] Pipeline is not initialized.111")
            raise PipelineNotInitializedException()
        audio = data[0]
        pitchf = data[1]
        feature = data[2]
        convertSize = data[3]
        vol = data[4]
        outSize = data[5]

        if vol < self.settings.silentThreshold:
            return np.zeros(convertSize).astype(np.int16) * np.sqrt(vol)

        if self.pipeline is not None:
            device = self.pipeline.device
        else:
            device = torch.device("cpu")
        audio = torch.from_numpy(audio).to(device=device, dtype=torch.float32)
        audio = torchaudio.functional.resample(audio, self.slotInfo.samplingRate, 16000, rolloff=0.99)
        repeat = 1 if self.settings.rvcQuality else 0
        sid = self.settings.dstId
        f0_up_key = self.settings.tran
        index_rate = self.settings.indexRatio
        protect = self.settings.protect

        if_f0 = 1 if self.slotInfo.f0 else 0
        embOutputLayer = self.slotInfo.embOutputLayer
        useFinalProj = self.slotInfo.useFinalProj

        try:
            audio_out, self.pitchf_buffer, self.feature_buffer = self.pipeline.exec(
                sid,
                audio,
                pitchf,
                feature,
                f0_up_key,
                index_rate,
                if_f0,
                self.settings.extraConvertSize / self.slotInfo.samplingRate if self.settings.silenceFront else 0.,  # extaraDataSizeの秒数。RVCのモデルのサンプリングレートで処理(★１)。
                embOutputLayer,
                useFinalProj,
                repeat,
                protect,
                outSize
            )
            result = audio_out.detach().cpu().numpy() * np.sqrt(vol)

            return result
        except DeviceCannotSupportHalfPrecisionException as e:  # NOQA
            logger.warn("[Device Manager] Device cannot support half precision. Fallback to float....")
            self.deviceManager.setForceTensor(True)
            self.initialize()
            # raise e

        return

    def __del__(self):
        del self.pipeline

        # print("---------- REMOVING ---------------")

        # remove_path = os.path.join("RVC")
        # sys.path = [x for x in sys.path if x.endswith(remove_path) is False]

        # for key in list(sys.modules):
        #     val = sys.modules.get(key)
        #     try:
        #         file_path = val.__file__
        #         if file_path.find("RVC" + os.path.sep) >= 0:
        #             # print("remove", key, file_path)
        #             sys.modules.pop(key)
        #     except Exception:  # type:ignore
        #         # print(e)
        #         pass

    def export2onnx(self):
        modelSlot = self.slotInfo

        if modelSlot.isONNX:
            logger.warn("[Voice Changer] export2onnx, No pyTorch filepath.")
            return {"status": "ng", "path": ""}

        if self.pipeline is not None:
            del self.pipeline
            self.pipeline = None

        torch.cuda.empty_cache()
        self.initialize()

        output_file_simple = export2onnx(self.settings.gpu, modelSlot)

        return {
            "status": "ok",
            "path": f"/tmp/{output_file_simple}",
            "filename": output_file_simple,
        }

    def get_model_current(self):
        return [
            {
                "key": "defaultTune",
                "val": self.settings.tran,
            },
            {
                "key": "defaultIndexRatio",
                "val": self.settings.indexRatio,
            },
            {
                "key": "defaultProtect",
                "val": self.settings.protect,
            },
        ]
