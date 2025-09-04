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
import json, time, os
from datetime import datetime
import asyncio


from backend.services.rag_service import get_rag_service
from backend.services.logger import setup_logger

router = APIRouter()
logger = setup_logger(__name__)

# ====== 追加: チャット履歴保存（JSONL） ======
# backend/api/chat.py → (.. / ..) → プロジェクトルート → frontend/logs/chat_log.json
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_LOG_DIR = os.path.join(_BASE_DIR, "frontend", "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "chat_log.json")

def _append_chat_log(entry: dict) -> None:
    """チャットログを1行JSONで追記。失敗しても本処理は止めない。"""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # ログ書き込み失敗は警告に留める
        logger.warning(f"failed to write chat log: {e}")

# ====== スキーマ ======
class ChatRequest(BaseModel):
    prompt: str

class BotRequest(BaseModel):
    prompt: str

class BotResponse(BaseModel):
    reply: str

@router.get("/health")
async def health():
    return {"status": "ok", "service": "kitakyushu-waste-chatbot"}

# ====== Blocking ======
@router.post("/chat/blocking")
async def chat_blocking(req: ChatRequest):
    try:
        rag = get_rag_service()
        res = rag.blocking_query(req.prompt, k=5)

        payload = {
            "response": res["response"],
            "latency": res["latency"],
            "timestamp": res["timestamp"],
            "context_found": res.get("documents", 0) > 0,
            "source_documents": res.get("documents", 0),
            "mode": "blocking",
        }

        # 追加: ログ保存
        _append_chat_log({
            "timestamp": res["timestamp"],
            "mode": "blocking",
            "prompt": req.prompt,
            "response": res["response"],
            "latency": res["latency"],
            "context_found": payload["context_found"],
            "source_documents": payload["source_documents"],
        })

        return payload
    except Exception as e:
        logger.error(f"blocking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ====== Streaming (SSE) ======
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
                await asyncio.sleep(0)
            done = {
                "type": "complete",
                "response": full,
                "latency": time.time() - start,
                "timestamp": datetime.now().isoformat()
            }

            # 追加: ログ保存（完了時にまとめて1件分を保存）
            _append_chat_log({
                "timestamp": done["timestamp"],
                "mode": "streaming",
                "prompt": req.prompt,
                "response": full,
                "latency": done["latency"],
                # streaming は docs 数を取得しないので None/0 を入れておく
                "context_found": None,
                "source_documents": None,
            })

            yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            gen(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control":"no-cache",
                "Connection":"keep-alive",
                "Content-Type":"text/event-stream; charset=utf-8",
                "X-Accel-Buffering": "no", 
            },
        )
    except Exception as e:
        logger.error(f"streaming error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ====== 後半課題の Blocking API 仕様 ======
@router.post("/bot/respond", response_model=BotResponse)
async def bot_respond(req: BotRequest):
    rag = get_rag_service()
    res = rag.blocking_query(req.prompt, k=5)

    # 追加: ログ保存
    _append_chat_log({
        "timestamp": res["timestamp"],
        "mode": "bot_blocking",
        "prompt": req.prompt,
        "response": res["response"],
        "latency": res["latency"],
        "context_found": (res.get("documents", 0) > 0),
        "source_documents": res.get("documents", 0),
    })

    return BotResponse(reply=res["response"])

# ====== 後半課題の Streaming API 仕様 ======
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

        # 追加: ログ保存
        _append_chat_log({
            "timestamp": done["timestamp"],
            "mode": "bot_streaming",
            "prompt": req.prompt,
            "response": full,
            "latency": done["latency"],
            "context_found": None,
            "source_documents": None,
        })

        yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control":"no-cache",
            "Connection":"keep-alive",
            "Content-Type":"text/event-stream; charset=utf-8"
        },
    )
