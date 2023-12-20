from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Cookie
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import ssl
import datetime
import datetime
from elasticsearch import Elasticsearch
from elasticsearch import helpers
app = FastAPI()

rooms_id = {} # 방 들  딕셔너리 값안에는 소켓들이 응집되어 있음



