# VoiceChanger API - W - OKADA  제작 모듈화 과정 

# RestApi 제작
## MMVC_File upload_file : class  <br>
 def uploadfile : 업로드 된 파일을 서버의 특정 디렉토리에 저장 처리 <br>
 def concat_file_chunks : 파일 청크들을 병합처리  하나의 파일로 병합  <br>
## MMVC_Rest_VoiceChanger : class <br>
### Rest_VoiceChanger : 바이트 배열을 받아서 base64 인코딩후 voice 로 디코딩하여 json형식으로  파일을 반환하는 형식 <br>
## def  __init__ : 클라이언트측에서 APIROUTER  POST 요청시 LCOK 을 통해 동시성 제어 <br>
### def test (self, voice: VoiceModel): <br>
 def something 