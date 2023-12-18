from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import socketio
import cv2
import numpy as np
from pathlib import Path  # pathlib 모듈 추가
app = FastAPI()

sio = socketio.AsyncServer(cors_allowed_origins="*")
# 현재 스크립트 파일의 디렉토리를 기반으로 static 디렉토리를 설정
current_directory = Path(__file__).parent
app.mount("/static", StaticFiles(directory=current_directory / "static"), name="static")


 
@app.get("/")
async def get():
    index_path = current_directory / "static" / "index.html"
    with open(index_path, "r", encoding="utf-8") as html_file:
        content = html_file.read()
    return HTMLResponse(content=content)



@app.websocket("/video")
async def video_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            # 클라이언트로부터 비디오 프레임 수신
            data = await websocket.receive_bytes()

            # 수신된 데이터를 NumPy 배열로 디코딩
            frame = np.frombuffer(data, dtype=np.uint8)

            # 디코딩된 프레임을 OpenCV를 사용하여 처리 (여기에서는 그대로 전송)
            # (실제로는 프레임을 처리하고 다시 클라이언트에 전송하는 로직을 추가해야 함)

            # 처리된 프레임을 클라이언트로 전송
            await websocket.send_bytes(frame.tobytes())

        except Exception as e:
            print(f"Error: {e}")
            break

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)

