 
from fastapi import APIRouter

# API 테스트로 보임 
class MMVC_Rest_Hello:
    def __init__(self):


        
        self.router = APIRouter()
        self.router.add_api_route("/api/hello", self.hello, methods=["GET"])

    def hello(self):
        return {"result": "Index"}
