from fastapi import APIRouter
from backend.services.gpu_moniter import GPUMonitor  # 改成带前缀 backend.

router = APIRouter()

@router.get("/monitor/gpu")
async def monitor_gpu():
    """GPU の使用状況"""
    return GPUMonitor.get_status()
