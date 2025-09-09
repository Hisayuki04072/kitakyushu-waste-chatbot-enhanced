import os
from fastapi import APIRouter, UploadFile, File, HTTPException

from backend.services.rag_service import get_rag_service

router = APIRouter()

# プロジェクトルート基準で data ディレクトリを作る
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
os.makedirs(DATA_DIR, exist_ok=True)

@router.get("/test")
async def test_rag_service():
    """RAGサービスのテスト用エンドポイント"""
    try:
        rag = get_rag_service()
        return {"status": "ok", "message": "RAGサービスが正常に初期化されました"}
    except Exception as e:
        return {"status": "error", "message": f"RAGサービス初期化エラー: {str(e)}"}

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    CSV/TXT をアップロードして知識ベースに取り込む
    - .csv: 行を文書化して Chroma に追加
    - .txt: 全文を 1 文書として追加
    """
    try:
        # まずRAGサービスが利用可能か確認
        rag = get_rag_service()
        
        save_path = os.path.join(DATA_DIR, file.filename)
        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)

        if file.filename.lower().endswith(".csv"):
            res = rag.add_csv(save_path)
            # BM25とアンサンブルレトリバーを再初期化
            rag._init_retrievers()
            return {"status": "ok", "filename": file.filename, "ingested": res.get("count", 0)}
        else:
            # テキスト等はそのまま 1 文書として追加
            text = content.decode("utf-8", errors="ignore")
            rag.vectorstore.add_texts([text], metadatas=[{"source": file.filename}])
            # BM25とアンサンブルレトリバーを再初期化
            rag._init_retrievers()
            return {"status": "ok", "filename": file.filename, "ingested": 1}

    except Exception as e:
        import traceback
        error_detail = f"エラー: {str(e)}\nトレースバック: {traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)
