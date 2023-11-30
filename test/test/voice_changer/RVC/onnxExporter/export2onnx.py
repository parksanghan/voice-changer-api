import os
import json
import torch
from onnxsim import simplify
import onnx
from const import TMP_DIR, EnumInferenceTypes
from data.ModelSlot import RVCModelSlot
from voice_changer.RVC.deviceManager.DeviceManager import DeviceManager
from voice_changer.RVC.onnxExporter.SynthesizerTrnMs256NSFsid_ONNX import (
    SynthesizerTrnMs256NSFsid_ONNX,
)
from voice_changer.RVC.onnxExporter.SynthesizerTrnMs256NSFsid_nono_ONNX import (
    SynthesizerTrnMs256NSFsid_nono_ONNX,
)
from voice_changer.RVC.onnxExporter.SynthesizerTrnMs768NSFsid_ONNX import (
    SynthesizerTrnMs768NSFsid_ONNX,
)
from voice_changer.RVC.onnxExporter.SynthesizerTrnMs768NSFsid_nono_ONNX import (
    SynthesizerTrnMs768NSFsid_nono_ONNX,
)
from voice_changer.RVC.onnxExporter.SynthesizerTrnMsNSFsidNono_webui_ONNX import (
    SynthesizerTrnMsNSFsidNono_webui_ONNX,
)
from voice_changer.RVC.onnxExporter.SynthesizerTrnMsNSFsid_webui_ONNX import (
    SynthesizerTrnMsNSFsid_webui_ONNX,
)
from voice_changer.VoiceChangerParamsManager import VoiceChangerParamsManager


def export2onnx(gpu: int, modelSlot: RVCModelSlot):
    vcparams = VoiceChangerParamsManager.get_instance().params
    modelFile = os.path.join(vcparams.model_dir, str(modelSlot.slotIndex), os.path.basename(modelSlot.modelFile))

    output_file = os.path.splitext(os.path.basename(modelFile))[0] + ".onnx"
    output_file_simple = os.path.splitext(os.path.basename(modelFile))[0] + "_simple.onnx"
    output_path = os.path.join(TMP_DIR, output_file)
    output_path_simple = os.path.join(TMP_DIR, output_file_simple)
    metadata = {
        "application": "VC_CLIENT",
        "version": "2.1",
        "modelType": modelSlot.modelType,
        "samplingRate": modelSlot.samplingRate,
        "f0": modelSlot.f0,
        "embChannels": modelSlot.embChannels,
        "embedder": modelSlot.embedder,
        "embOutputLayer": modelSlot.embOutputLayer,
        "useFinalProj": modelSlot.useFinalProj,
    }
    gpuMomory = DeviceManager.get_instance().getDeviceMemory(gpu)
    print(f"[Voice Changer] exporting onnx... gpu_id:{gpu} gpu_mem:{gpuMomory}")

    if gpuMomory > 0:
        _export2onnx(modelFile, output_path, output_path_simple, True, metadata)
    else:
        print("[Voice Changer] Warning!!! onnx export with float32. maybe size is doubled.")
        _export2onnx(modelFile, output_path, output_path_simple, False, metadata)
    return output_file_simple


def _export2onnx(input_model, output_model, output_model_simple, is_half, metadata):
    cpt = torch.load(input_model, map_location="cpu")
    if is_half:
        dev = torch.device("cuda", index=0)
    else:
        dev = torch.device("cpu")

    # EnumInferenceTypesのままだとシリアライズできないのでテキスト化
    if metadata["modelType"] == EnumInferenceTypes.pyTorchRVC.value:
        net_g_onnx = SynthesizerTrnMs256NSFsid_ONNX(*cpt["config"], is_half=is_half)
    elif metadata["modelType"] == EnumInferenceTypes.pyTorchWebUI.value:
        net_g_onnx = SynthesizerTrnMsNSFsid_webui_ONNX(**cpt["params"], is_half=is_half)
    elif metadata["modelType"] == EnumInferenceTypes.pyTorchRVCNono.value:
        net_g_onnx = SynthesizerTrnMs256NSFsid_nono_ONNX(*cpt["config"])
    elif metadata["modelType"] == EnumInferenceTypes.pyTorchWebUINono.value:
        net_g_onnx = SynthesizerTrnMsNSFsidNono_webui_ONNX(**cpt["params"])
    elif metadata["modelType"] == EnumInferenceTypes.pyTorchRVCv2.value:
        net_g_onnx = SynthesizerTrnMs768NSFsid_ONNX(*cpt["config"], is_half=is_half)
    elif metadata["modelType"] == EnumInferenceTypes.pyTorchRVCv2Nono.value:
        net_g_onnx = SynthesizerTrnMs768NSFsid_nono_ONNX(*cpt["config"])
    else:
        print(
            "unknwon::::: ",
            metadata["modelType"],
            EnumInferenceTypes.pyTorchRVCv2.value,
        )

    net_g_onnx.eval().to(dev)
    net_g_onnx.load_state_dict(cpt["weight"], strict=False)
    if is_half:
        net_g_onnx = net_g_onnx.half()
    
    featsLength = 64

    if is_half:
        feats = torch.HalfTensor(1, featsLength, metadata["embChannels"]).to(dev)
    else:
        feats = torch.FloatTensor(1, featsLength, metadata["embChannels"]).to(dev)
    p_len = torch.LongTensor([featsLength]).to(dev)
    sid = torch.LongTensor([0]).to(dev)

    if metadata["f0"] is True:
        pitch = torch.zeros(1, featsLength, dtype=torch.int64).to(dev)
        pitchf = torch.FloatTensor(1, featsLength).to(dev)
        input_names = ["feats", "p_len", "pitch", "pitchf", "sid"]
        inputs = (
            feats,
            p_len,
            pitch,
            pitchf,
            sid,
        )

    else:
        input_names = ["feats", "p_len", "sid"]
        inputs = (
            feats,
            p_len,
            sid,
        )

    output_names = [
        "audio",
    ]

    torch.onnx.export(
        net_g_onnx,
        inputs,
        output_model,
        dynamic_axes={
            "feats": [1],
            "pitch": [1],
            "pitchf": [1],
        },
        do_constant_folding=False,
        opset_version=17,
        verbose=False,
        input_names=input_names,
        output_names=output_names,
    )

    model_onnx2 = onnx.load(output_model)
    model_simp, check = simplify(model_onnx2)
    meta = model_simp.metadata_props.add()
    meta.key = "metadata"
    meta.value = json.dumps(metadata)
    onnx.save(model_simp, output_model_simple)
