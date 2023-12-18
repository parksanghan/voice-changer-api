from fastapi.testclient import TestClient
from voice_changer.VoiceChangerManager import VoiceChangerManager
from const import UPLOAD_DIR
from restapi.MMVC_Rest import MMVC_Rest
from voice_changer.utils.VoiceChangerParams import VoiceChangerParams

def main():
    # 예시: VoiceChangerManager 인스턴스 생성
    voice_changer_manager_instance = VoiceChangerManager()

    # 예시: VoiceChangerParams 설정
    # voice_changer_params = ...
    voice_changer_params = VoiceChangerParams()
    #14개
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
 
    # 예시: MMVC_Rest 인스턴스 생성하기 
    rest_instance = MMVC_Rest.get_instance(
        voiceChangerManager=voice_changer_manager_instance,
        voiceChangerParams=voice_changer_params,
    )

    # 예시: FastAPI TestClient 생성
    client = TestClient(rest_instance)

    # 예시: WAV 파일 경로 설정
    wav_file_path = "/path/to/your/wav/file.wav"

    try:
        # 예시: WAV 파일 업로드
        with open(wav_file_path, "rb") as wav_file:
            response_upload = client.post("/upload_file", files={"file": ("test.wav", wav_file)})

        # 예시: 업로드 결과 확인
        assert response_upload.status_code == 200

        # 예시: 업로드한 파일 정보 가져오기
        uploaded_file_info = response_upload.json()
        uploaded_filename = uploaded_file_info.get("filename")

        # 예시: 업로드한 WAV 파일에 대한 음성 변환 요청
        response_transform = client.post("/test", json={"timestamp": 123, "buffer": uploaded_filename})

        # 예시: 변환 결과 확인
        assert response_transform.status_code == 200
        transformed_data = response_transform.json()
        print("Transformed data:", transformed_data)

    except Exception as e:
        print("Error during testing:", e)

if __name__ == "__main__":
    main()
