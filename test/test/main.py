from fastapi.testclient import TestClient
from voice_changer.VoiceChangerManager import VoiceChangerManager
from const import UPLOAD_DIR
from restapi.MMVC_Rest import MMVC_Rest
from voice_changer.utils.VoiceChangerParams import VoiceChangerParams

def main():
    # ����: VoiceChangerManager �ν��Ͻ� ����
    voice_changer_manager_instance = VoiceChangerManager()

    # ����: VoiceChangerParams ����
    # voice_changer_params = ...
    voice_changer_params = VoiceChangerParams()
    #14��
    # VoiceChangerParams
    # model_dir: str
    #content_vec_500: str
    #content_vec_500_onnx: str
    #content_vec_500_onnx_on: bool
    #hubert_base: str
    #hubert_base_jp: str
    #hubert_soft: str
    #nsf_hifigan: str
    #sample_mode: str
    #crepe_onnx_full: str
    #crepe_onnx_tiny: str
    #rmvpe: str
    #rmvpe_onnx: str
 
    # ����: MMVC_Rest �ν��Ͻ� �����ϱ� 
    rest_instance = MMVC_Rest.get_instance(
        voiceChangerManager=voice_changer_manager_instance,
        voiceChangerParams=voice_changer_params,
    )

    # ����: FastAPI TestClient ����
    client = TestClient(rest_instance)

    # ����: WAV ���� ��� ����
    wav_file_path = "/path/to/your/wav/file.wav"

    try:
        # ����: WAV ���� ���ε�
        with open(wav_file_path, "rb") as wav_file:
            response_upload = client.post("/upload_file", files={"file": ("test.wav", wav_file)})

        # ����: ���ε� ��� Ȯ��
        assert response_upload.status_code == 200

        # ����: ���ε��� ���� ���� ��������
        uploaded_file_info = response_upload.json()
        uploaded_filename = uploaded_file_info.get("filename")

        # ����: ���ε��� WAV ���Ͽ� ���� ���� ��ȯ ��û
        response_transform = client.post("/test", json={"timestamp": 123, "buffer": uploaded_filename})

        # ����: ��ȯ ��� Ȯ��
        assert response_transform.status_code == 200
        transformed_data = response_transform.json()
        print("Transformed data:", transformed_data)

    except Exception as e:
        print("Error during testing:", e)

if __name__ == "__main__":
    main()
