from fastapi import APIRouter
from ..services.gpu_moniter import GPUMonitor  # 改成带前缀 backend.
from ..services.rag_service import get_rag_service

router = APIRouter()

@router.get("/monitor/gpu")
async def monitor_gpu():
    """GPU の使用状況"""
    return GPUMonitor.get_status()

@router.get("/monitor/rag")
async def monitor_rag():
    """RAGサービスの状況（ベクトルDB登録データ数など）"""
    try:
        rag_service = get_rag_service()
        return rag_service.get_search_info()
    except Exception as e:
        return {"error": str(e)}

@router.post("/monitor/rag/fix")
async def fix_rag_inconsistency():
    """RAGサービスのデータ不整合を修正"""
    try:
        rag_service = get_rag_service()
        return rag_service.fix_data_inconsistency()
    except Exception as e:
        return {"error": str(e)}
