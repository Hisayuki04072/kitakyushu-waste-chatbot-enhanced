"""
チャットAPI:
- /api/chat/blocking  : 同期応答
- /api/chat/streaming : SSE でストリーミング応答
- /api/bot/respond    : 後半課題の blocking API
- /api/bot/stream     : 後半課題の streaming API
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json, time
from datetime import datetime

from backend.services.rag_service import get_rag_service
from backend.services.logger import setup_logger

router = APIRouter()
logger = setup_logger(__name__)

class ChatRequest(BaseModel):
    prompt: str

class BotRequest(BaseModel):
    prompt: str

class BotResponse(BaseModel):
    reply: str

@router.get("/health")
async def health():
    return {"status": "ok", "service": "kitakyushu-waste-chatbot"}

@router.post("/chat/blocking")
async def chat_blocking(req: ChatRequest):
    try:
        rag = get_rag_service()
        res = rag.blocking_query(req.prompt, k=5)
        return {
            "response": res["response"],
            "latency": res["latency"],
            "timestamp": res["timestamp"],
            "context_found": res.get("documents", 0) > 0,
            "source_documents": res.get("documents", 0),
            "mode": "blocking",
        }
    except Exception as e:
        logger.error(f"blocking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat/streaming")
async def chat_streaming(req: ChatRequest):
    try:
        rag = get_rag_service()
        start = time.time()

        async def gen():
            full = ""
            async for chunk in rag.streaming_query(req.prompt, k=5):
                full += chunk
                yield f"data: {json.dumps({'type':'chunk','content':chunk}, ensure_ascii=False)}\n\n"
            done = {
                "type": "complete",
                "response": full,
                "latency": time.time() - start,
                "timestamp": datetime.now().isoformat()
            }
            yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            gen(),
            media_type="text/event-stream; charset=utf-8",
            headers={"Cache-Control":"no-cache","Connection":"keep-alive","Content-Type":"text/event-stream; charset=utf-8"},
        )
    except Exception as e:
        logger.error(f"streaming error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 後半課題の Blocking API 仕様
@router.post("/bot/respond", response_model=BotResponse)
async def bot_respond(req: BotRequest):
    rag = get_rag_service()
    res = rag.blocking_query(req.prompt, k=5)
    return BotResponse(reply=res["response"])

# 後半課題の Streaming API 仕様
@router.post("/bot/stream")
async def bot_stream(req: BotRequest):
    rag = get_rag_service()
    start = time.time()

    async def gen():
        full = ""
        async for chunk in rag.streaming_query(req.prompt, k=5):
            full += chunk
            yield f"data: {json.dumps({'type':'chunk','content':chunk}, ensure_ascii=False)}\n\n"
        done = {
            "type":"complete",
            "reply": full,
            "latency": time.time() - start,
            "timestamp": datetime.now().isoformat()
        }
        yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control":"no-cache","Connection":"keep-alive","Content-Type":"text/event-stream; charset=utf-8"},
    )
