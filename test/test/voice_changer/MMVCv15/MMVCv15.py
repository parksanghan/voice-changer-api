import sys
import os
from data.ModelSlot import MMVCv15ModelSlot
from voice_changer.VoiceChangerParamsManager import VoiceChangerParamsManager
from voice_changer.utils.VoiceChangerModel import AudioInOut, VoiceChangerModel

if sys.platform.startswith("darwin"):
    baseDir = [x for x in sys.path if x.endswith("Contents/MacOS")]
    if len(baseDir) != 1:
        print("baseDir should be only one ", baseDir)
        sys.exit()
    modulePath = os.path.join(baseDir[0], "MMVC_Client_v15", "python")
    sys.path.append(modulePath)
else:
    modulePath = os.path.join("MMVC_Client_v15", "python")
    sys.path.append(modulePath)

from dataclasses import dataclass, asdict
import numpy as np
import torch
import onnxruntime
import pyworld as pw

from voice_changer.MMVCv15.models.models import SynthesizerTrn  # type:ignore
from voice_changer.MMVCv15.client_modules import (
    convert_continuos_f0,
    spectrogram_torch,
    get_hparams_from_file,
    load_checkpoint,
)

from Exceptions import NoModeLoadedException, ONNXInputArgumentException

providers = [
    "OpenVINOExecutionProvider",
    "CUDAExecutionProvider",
    "DmlExecutionProvider",
    "CPUExecutionProvider",
]


@dataclass
class MMVCv15Settings:
    gpu: int = -9999
    srcId: int = 0
    dstId: int = 101

    f0Factor: float = 1.0
    f0Detector: str = "dio"  # dio or harvest

    maxInputLength: int = 1024

    # ↓mutableな物だけ列挙
    intData = ["gpu", "srcId", "dstId"]
    floatData = ["f0Factor"]
    strData = ["f0Detector"]


class MMVCv15(VoiceChangerModel):
    def __init__(self, slotInfo: MMVCv15ModelSlot):
        print("[Voice Changer] [MMVCv15] Creating instance ")
        self.voiceChangerType = "MMVCv15"
        self.settings = MMVCv15Settings()
        self.net_g = None
        self.onnx_session: onnxruntime.InferenceSession | None = None

        self.gpu_num = torch.cuda.device_count()

        self.slotInfo = slotInfo
        self.audio_buffer: AudioInOut | None = None
        self.initialize()

    def initialize(self):
        print("[Voice Changer] [MMVCv15] Initializing... ")
        vcparams = VoiceChangerParamsManager.get_instance().params
        configPath = os.path.join(
            vcparams.model_dir, str(self.slotInfo.slotIndex), self.slotInfo.configFile
        )
        modelPath = os.path.join(
            vcparams.model_dir, str(self.slotInfo.slotIndex), self.slotInfo.modelFile
        )

        self.hps = get_hparams_from_file(configPath)

        self.net_g = SynthesizerTrn(
            spec_channels=self.hps.data.filter_length // 2 + 1,
            segment_size=self.hps.train.segment_size // self.hps.data.hop_length,
            inter_channels=self.hps.model.inter_channels,
            hidden_channels=self.hps.model.hidden_channels,
            upsample_rates=self.hps.model.upsample_rates,
            upsample_initial_channel=self.hps.model.upsample_initial_channel,
            upsample_kernel_sizes=self.hps.model.upsample_kernel_sizes,
            n_flow=self.hps.model.n_flow,
            dec_out_channels=1,
            dec_kernel_size=7,
            n_speakers=self.hps.data.n_speakers,
            gin_channels=self.hps.model.gin_channels,
            requires_grad_pe=self.hps.requires_grad.pe,
            requires_grad_flow=self.hps.requires_grad.flow,
            requires_grad_text_enc=self.hps.requires_grad.text_enc,
            requires_grad_dec=self.hps.requires_grad.dec,
        )
        self.settings.maxInputLength = 128 * 2048  # Torchの時は無制限。とりあえずでかい値で初期化

        if self.slotInfo.isONNX:
            self.onxx_input_length = 8192
            providers, options = self.getOnnxExecutionProvider()
            self.onnx_session = onnxruntime.InferenceSession(
                modelPath,
                providers=providers,
                provider_options=options,
            )
            inputs_info = self.onnx_session.get_inputs()
            for i in inputs_info:
                # print("ONNX INPUT SHAPE", i.name, i.shape)
                if i.name == "sin":
                    self.onxx_input_length = i.shape[2]
                    self.settings.maxInputLength = (
                        self.onxx_input_length
                        - (0.012 * self.hps.data.sampling_rate)
                        - 1024
                    )  # onnxの場合は入力長固(crossfadeの1024は仮) # NOQA
        else:
            self.net_g.eval()
            load_checkpoint(modelPath, self.net_g, None)

        # その他の設定
        self.settings.srcId = self.slotInfo.srcId
        self.settings.dstId = self.slotInfo.dstId
        self.settings.f0Factor = self.slotInfo.f0Factor

        print("[Voice Changer] [MMVCv15] Initializing... done")

    def getOnnxExecutionProvider(self):
        availableProviders = onnxruntime.get_available_providers()
        devNum = torch.cuda.device_count()
        if (
            self.settings.gpu >= 0
            and "CUDAExecutionProvider" in availableProviders
            and devNum > 0
        ):
            return ["CUDAExecutionProvider"], [{"device_id": self.settings.gpu}]
        elif self.settings.gpu >= 0 and "DmlExecutionProvider" in availableProviders:
            return ["DmlExecutionProvider"], [{}]
        else:
            return ["CPUExecutionProvider"], [
                {
                    "intra_op_num_threads": 8,
                    "execution_mode": onnxruntime.ExecutionMode.ORT_PARALLEL,
                    "inter_op_num_threads": 8,
                }
            ]

    def update_settings(self, key: str, val: int | float | str):
        if key in self.settings.intData:
            val = int(val)
            setattr(self.settings, key, val)
            if key == "gpu" and self.slotInfo.isONNX:
                providers, options = self.getOnnxExecutionProvider()
                vcparams = VoiceChangerParamsManager.get_instance().params
                modelPath = os.path.join(
                    vcparams.model_dir,
                    str(self.slotInfo.slotIndex),
                    self.slotInfo.modelFile,
                )
                self.onnx_session = onnxruntime.InferenceSession(
                    modelPath,
                    providers=providers,
                    provider_options=options,
                )
                inputs_info = self.onnx_session.get_inputs()
                for i in inputs_info:
                    if i.name == "sin":
                        self.onxx_input_length = i.shape[2]
                        self.settings.maxInputLength = (
                            self.onxx_input_length
                            - (0.012 * self.hps.data.sampling_rate)
                            - 1024
                        )  # onnxの場合は入力長固(crossfadeの1024は仮) # NOQA
        elif key in self.settings.floatData:
            setattr(self.settings, key, float(val))
        elif key in self.settings.strData:
            setattr(self.settings, key, str(val))
        else:
            return False

        return True

    def get_info(self):
        data = asdict(self.settings)

        data["onnxExecutionProviders"] = (
            self.onnx_session.get_providers() if self.onnx_session is not None else []
        )
        return data

    def get_processing_sampling_rate(self):
        if hasattr(self, "hps") is False:
            raise NoModeLoadedException("config")
        return self.hps.data.sampling_rate

    def _get_f0(self, detector: str, newData: AudioInOut):
        audio_norm_np = newData.astype(np.float64)
        if detector == "dio":
            _f0, _time = pw.dio(
                audio_norm_np, self.hps.data.sampling_rate, frame_period=5.5
            )
            f0 = pw.stonemask(audio_norm_np, _f0, _time, self.hps.data.sampling_rate)
        else:
            f0, t = pw.harvest(
                audio_norm_np,
                self.hps.data.sampling_rate,
                frame_period=5.5,
                f0_floor=71.0,
                f0_ceil=1000.0,
            )
        f0 = convert_continuos_f0(
            f0, int(audio_norm_np.shape[0] / self.hps.data.hop_length)
        )
        f0 = torch.from_numpy(f0.astype(np.float32))
        return f0

    def _get_spec(self, newData: AudioInOut):
        audio = torch.FloatTensor(newData)
        audio_norm = audio.unsqueeze(0)  # unsqueeze
        spec = spectrogram_torch(
            audio_norm,
            self.hps.data.filter_length,
            self.hps.data.sampling_rate,
            self.hps.data.hop_length,
            self.hps.data.win_length,
            center=False,
        )
        spec = torch.squeeze(spec, 0)
        return spec

    def generate_input(
        self,
        newData: AudioInOut,
        inputSize: int,
        crossfadeSize: int,
        solaSearchFrame: int = 0,
    ):
        # maxInputLength を更新(ここでやると非効率だが、とりあえず。)
        if self.slotInfo.isONNX:
            self.settings.maxInputLength = (
                self.onxx_input_length - crossfadeSize - solaSearchFrame
            )  # onnxの場合は入力長固(crossfadeの1024は仮) # NOQA get_infoで返る値。この関数内の処理では使わない。

        newData = newData.astype(np.float32) / self.hps.data.max_wav_value

        if self.audio_buffer is not None:
            self.audio_buffer = np.concatenate(
                [self.audio_buffer, newData], 0
            )  # 過去のデータに連結
        else:
            self.audio_buffer = newData

        convertSize = inputSize + crossfadeSize + solaSearchFrame

        # if convertSize < 8192:
        #     convertSize = 8192
        if convertSize % self.hps.data.hop_length != 0:  # モデルの出力のホップサイズで切り捨てが発生するので補う。
            convertSize = convertSize + (
                self.hps.data.hop_length - (convertSize % self.hps.data.hop_length)
            )

        # ONNX は固定長
        if self.slotInfo.isONNX:
            convertSize = self.onxx_input_length

        convertOffset = -1 * convertSize
        self.audio_buffer = self.audio_buffer[convertOffset:]  # 変換対象の部分だけ抽出

        f0 = self._get_f0(self.settings.f0Detector, self.audio_buffer)  # torch
        f0 = (f0 * self.settings.f0Factor).unsqueeze(0).unsqueeze(0)
        spec = self._get_spec(self.audio_buffer)  # torch
        sid = torch.LongTensor([int(self.settings.srcId)])
        return [spec, f0, sid]

    def _onnx_inference(self, data):
        spec, f0, sid_src = data
        spec = spec.unsqueeze(0)
        spec_lengths = torch.tensor([spec.size(2)])
        sid_tgt1 = torch.LongTensor([self.settings.dstId])
        sin, d = self.net_g.make_sin_d(f0)
        (d0, d1, d2, d3) = d
        audio1 = (
            self.onnx_session.run(
                ["audio"],
                {
                    "specs": spec.numpy(),
                    "lengths": spec_lengths.numpy(),
                    "sin": sin.numpy(),
                    "d0": d0.numpy(),
                    "d1": d1.numpy(),
                    "d2": d2.numpy(),
                    "d3": d3.numpy(),
                    "sid_src": sid_src.numpy(),
                    "sid_tgt": sid_tgt1.numpy(),
                },
            )[0][0, 0]
            * self.hps.data.max_wav_value
        )
        return audio1

    def _pyTorch_inference(self, data):
        if self.settings.gpu < 0 or self.gpu_num == 0:
            dev = torch.device("cpu")
        else:
            dev = torch.device("cuda", index=self.settings.gpu)

        with torch.no_grad():
            spec, f0, sid_src = data
            spec = spec.unsqueeze(0).to(dev)
            spec_lengths = torch.tensor([spec.size(2)]).to(dev)
            f0 = f0.to(dev)
            sid_src = sid_src.to(dev)
            sid_target = torch.LongTensor([self.settings.dstId]).to(dev)

            audio1 = (
                self.net_g.to(dev)
                .voice_conversion(spec, spec_lengths, f0, sid_src, sid_target)[0, 0]
                .data
                * self.hps.data.max_wav_value
            )
            result = audio1.float().cpu().numpy()
        return result

    def inference(self, data):
        try:
            if self.slotInfo.isONNX:
                audio = self._onnx_inference(data)
            else:
                audio = self._pyTorch_inference(data)
            return audio
        except onnxruntime.capi.onnxruntime_pybind11_state.InvalidArgument as _e:
            print(_e)
            raise ONNXInputArgumentException()

    def __del__(self):
        del self.net_g
        del self.onnx_session

        remove_path = os.path.join("MMVC_Client_v15", "python")
        sys.path = [x for x in sys.path if x.endswith(remove_path) is False]

        for key in list(sys.modules):
            val = sys.modules.get(key)
            try:
                file_path = val.__file__
                if file_path.find(remove_path + os.path.sep) >= 0:
                    # print("remove", key, file_path)
                    sys.modules.pop(key)
            except:  # NOQA
                pass

    def get_model_current(self):
        return [
            {
                "key": "srcId",
                "val": self.settings.srcId,
            },
            {
                "key": "dstId",
                "val": self.settings.dstId,
            },
            {
                "key": "f0Factor",
                "val": self.settings.f0Factor,
            },
        ]
