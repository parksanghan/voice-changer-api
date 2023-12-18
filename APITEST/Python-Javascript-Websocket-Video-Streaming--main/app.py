from fastapi import FastAPI, Depends , Request ,requests 
from fastapi_socketio import SocketManager
import uvicorn 
app = FastAPI()
socket_manager = SocketManager(app, cors_allowed_origins="*")

user_rooms= {}
room_users = {}
names_user = {}
socket_manager.enter_room()
# FastAPI 경로 핸들러 예제
@app.get("/join/{client_id}")
async def join(client_id:str , request : Request):
    display_name = request._query_params.get('display_name')
    mute_audio = request.query_params.get('mute_audio')
    mute_video = request.query_params.get('mute_video')
    room_id = request.query_params.get('room_id')

    return {"dispalyname": "{displayname},Mic : {mute_mic}, Video :  {mute_vid} "}

# SocketIO 이벤트 핸들러 예제
@socket_manager.on("connect")
async def handle_connect(sid, environ):
    print(f"Client {sid} connected")
    socket_manager.emit(sid,)

@socket_manager.on("disconnect")
async def handle_disconnect(sid):
    print(f"Client {sid} disconnected")
 

@app.get("/items/")
def read_item(query_param: str = Depends(get_query_param)):
    return {"query_param": query_param}