from flask import Flask, render_template, request, session
from flask_socketio import SocketIO, emit, join_room
import platform
import ssl
from elasticsearch import Elasticsearch
from elasticsearch import helpers
import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = "wubba lubba dub dub"

socketio = SocketIO(app)
zoom_rooms  = {}
users_in_room = {}
rooms_sid = {}
names_sid = {}

# elk 
es = Elasticsearch('http://192.168.56.103:9200')
es.info()

def utc_time():  # @timestamp timezone을 utc로 설정하여 kibana로 index 생성시 참조
    return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

def make_index(es, index_name):
    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
        es.indices.create(index=index_name)

index_name= 'webrtc_room'

@app.route("/join", methods=["GET"])
def join():
    display_name = request.args.get('display_name')
    mute_audio = request.args.get('mute_audio') # 1 or 0
    mute_video = request.args.get('mute_video') # 1 or 0
    room_id = request.args.get('room_id')
    session[room_id] = {"name": display_name,
                        "mute_audio": mute_audio, "mute_video": mute_video}
    return render_template("join.html", room_id=room_id, display_name=session[room_id]["name"], mute_audio=session[room_id]["mute_audio"], mute_video=session[room_id]["mute_video"])


@socketio.on("connect")
def on_connect():
    sid = request.sid
    print("New socket connected ", sid)


@socketio.on("join-room")
def on_join_room(data):
    sid = request.sid # 현재 클라이언트의 sid 얻기
    room_id = data["room_id"]
    display_name = session[room_id]["name"]

    # register sid to the room
    join_room(room_id)
    rooms_sid[sid] = room_id# 여기서 클라이언트 sid를 room_id에 매핑
    names_sid[sid] = display_name

    # broadcast to others in the room
    print("[{}] New member joined: {}<{}>".format(room_id, display_name, sid))

    # elk
    date = datetime.datetime.now()
    now = date.strftime('%m/%d/%y %H:%M:%S')
    doc_join1= {"des":"New member joined", "room_id":room_id, "sid": sid, "@timestamp": utc_time()}
    es.index(index=index_name, doc_type="log", body=doc_join1)
    
    emit("user-connect", {"sid": sid, "name": display_name},
         broadcast=True, include_self=False, room=room_id)

    # add to user list maintained on server
    if room_id not in users_in_room:
        users_in_room[room_id] = [sid]
        emit("user-list", {"my_id": sid})  # send own id only
    else:
        usrlist = {u_id: names_sid[u_id]
                   for u_id in users_in_room[room_id]}
        # send list of existing users to the new member
        emit("user-list", {"list": usrlist, "my_id": sid})
        # add new member to user list maintained on server
        users_in_room[room_id].append(sid)

    print("\nusers: ", users_in_room, "\n")


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    room_id = rooms_sid[sid]
    display_name = names_sid[sid]

    now = datetime.datetime.now()
    now = now.strftime('%m/%d/%y %H:%M:%S')
    doc_disconnect= {"des":"user-disconnect", "room_id":room_id, "sid": sid, "@timestamp": utc_time()}
    es.index(index=index_name, doc_type="log", body=doc_disconnect)

    print("[{}] Member left: {}<{}>".format(room_id, display_name, sid))
    emit("user-disconnect", {"sid": sid},
         broadcast=True, include_self=False, room=room_id)

    users_in_room[room_id].remove(sid)
    if len(users_in_room[room_id]) == 0:
        users_in_room.pop(room_id)

    rooms_sid.pop(sid)
    names_sid.pop(sid)

    print("\nusers: ", users_in_room, "\n")


@socketio.on("data")
def on_data(data):
    sender_sid = data['sender_id']
    target_sid = data['target_id']
    if sender_sid != request.sid:
        print("[Not supposed to happen!] request.sid and sender_id don't match!!!")

    if data["type"] != "new-ice-candidate":
        print('{} message from {} to {}'.format(
            data["type"], sender_sid, target_sid))
    socketio.emit('data', data, room=target_sid)


if __name__ == '__main__':
    socketio.run(app,
host="0.0.0.0",
port=5000,
debug=True,
reloader_options=True,
use_reloader=True
ssl_context=("cert.pem", "key.pem"))
make_index(es, index_name)