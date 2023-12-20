from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Cookie
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import ssl
import datetime
import datetime
from elasticsearch import Elasticsearch
from elasticsearch import helpers

app = FastAPI()
templates = Jinja2Templates(directory="static")

# 방 들이 저장된 변수 
rooms =  {}
# 사용자가 저장될 변수
users_in_room = {}
# 방이 저장될 변수          
rooms_sid = {} # 방안에 있는 사람들의 sid 값임 

# 사람의 이름 저장될 변수 
names_sid = {} # 이름에 들어있는 sid 값임 

# elk
#es = Elasticsearch('http://192.168.56.103:9200')
#es.info()

# def utc_time():  # @timestamp timezone을 utc로 설정하여 kibana로 index 생성시 참조
#     return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

#index_name = 'webrtc_room'




@app.get("/join")
def join(
    display_name: str,
    mute_audio: int,
    mute_video: int,
    room_id: str
):
    session = Cookie{"name": display_name, "mute_audio": mute_audio, "mute_video": mute_video}
    return templates.TemplateResponse("index.html", {"request": session, "room_id": room_id})

@app.get("/makeroom/{room_id}")
def makeroom(
    display_name: str,
    mute_audio: int,
    mute_video: int,
    room_id: str
):  
    if rooms.__contains__(room_id)==False:
        session = Cookie{"name": display_name, "mute_audio": mute_audio, "mute_video": mute_video}
        return templates.TemplateResponse("index.html", {"request": session, "room_id": room_id})
    else:
    

@app.get("/joinroom/{room_id}")
def joinroom(
    display_name: str,
    mute_audio: int,
    mute_video: int,
    room_id: str
):
    session = Cookie{"name": display_name, "mute_audio": mute_audio, "mute_video": mute_video}
    return templates.TemplateResponse("index.html", {"request": session, "room_id": room_id})
@app.get("/deleteroom/{client_id}/{room_id}")
def deleteroom(
    client_id : int, # 교수 id 인지 유효성 검사 
    room_id : str  # 있는  방인지 유효성 검사 
):
    if(rooms.__contains__(room_id) & users_in_room.__contains__(client_id) )== True:
        del rooms[room_id]
    




class WebSocketConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        self.active_connections.append(websocket)
        sid = websocket.client.id if hasattr(websocket.client, "id") else None #
        if sid:
            rooms_sid[sid] = room_id
            names_sid[sid] = websocket.client.session.get("name", "")

            usrlist = {u.client.id: names_sid[u.client.id] for u in self.active_connections}
            await websocket.send_json({"list": usrlist, "my_id": sid})

            print("[{}] New member joined: {}<{}>".format(room_id, names_sid[sid], sid))

            # elk
            #doc_join1 = {"des": "New member joined", "room_id": room_id, "sid": sid, "@timestamp": utc_time()}
            #es.index(index=index_name, doc_type="log", body=doc_join1)

            for connection in self.active_connections.count:##
                if connection != sid: #
                    await connection.send_json({"user-connect": {"sid": sid, "name": names_sid[sid]}}) #
        else:
            print("WebSocket client does not have an 'id' attribute.")

    # 나머지 코드는 이전과 동일합니다.


    # 나머지 코드는 이전과 동일합니다.

    async def disconnect(self, websocket: WebSocket):
        sid = websocket.client.id
        room_id = rooms_sid[sid]
        display_name = names_sid[sid]

        print("[{}] Member left: {}<{}>".format(room_id, display_name, sid))

        # elk
        #doc_disconnect = {"des": "user-disconnect", "room_id": room_id, "sid": sid, "@timestamp": utc_time()}
        #es.index(index=index_name, doc_type="log", body=doc_disconnect)

        usrlist = {u.client.id: names_sid[u.client.id] for u in self.active_connections}#
        await self.broadcast({"user-disconnect": {"sid": sid}, "list": usrlist}, room_id, sender_sid=sid)

        self.active_connections.remove(websocket)
        rooms_sid.pop(sid)
        names_sid.pop(sid)

    async def broadcast(self, message, room_id: str, sender_sid: str = None):
        for connection in self.active_connections:
            if connection.client != sender_sid:
                await connection.send_json(message)

manager = WebSocketConnectionManager()

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await manager.connect(websocket, room_id)
    try:
        while True:
            data = await websocket.receive_json()
            print("Received data:", data)  # 추가된 부분
            target_sid = data.get333('target_id', None)#
            await manager.broadcast(data, room_id, sender_sid=websocket.client.id)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "Video_server_websocket:app",
        host="0.0.0.0",
        port=5000,
        reload=True
    )