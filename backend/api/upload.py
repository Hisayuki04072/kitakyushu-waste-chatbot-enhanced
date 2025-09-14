import os
from fastapi import APIRouter, UploadFile, File, HTTPException

from ..services.rag_service import get_rag_service

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

@router.post("/")
async def upload_file(file: UploadFile = File(...)):
    """
    CSV/TXT をアップロードして知識ベースに取り込む
    - .csv: 行を文書化して Chroma に追加
    - .txt: 全文を 1 文書として追加
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"アップロード開始: {file.filename}")
        
        # まずRAGサービスが利用可能か確認
        logger.info("RAGサービス取得中...")
        rag = get_rag_service()
        logger.info("RAGサービス取得完了")
        
        save_path = os.path.join(DATA_DIR, file.filename)
        logger.info(f"ファイル保存先: {save_path}")
        
        content = await file.read()
        logger.info(f"ファイル読み込み完了: {len(content)} bytes")
        
        with open(save_path, "wb") as f:
            f.write(content)
        logger.info("ファイル保存完了")

        if file.filename.lower().endswith(".csv"):
            logger.info("CSV処理開始")
            res = rag.add_csv(save_path)
            logger.info(f"CSV処理完了: {res}")
            
            # BM25とアンサンブルレトリバーを再初期化
            logger.info("レトリバー初期化開始")
            rag._init_retrievers()
            logger.info("レトリバー初期化完了")
            
            return {"status": "ok", "filename": file.filename, "ingested": res.get("count", 0)}
        else:
            logger.info("テキストファイル処理開始")
            # テキスト等はそのまま 1 文書として追加
            text = content.decode("utf-8", errors="ignore")
            logger.info(f"テキストデコード完了: {len(text)} 文字")
            
            rag.vectorstore.add_texts([text], metadatas=[{"source": file.filename}])
            logger.info("ベクトルストア追加完了")
            
            # BM25とアンサンブルレトリバーを再初期化
            logger.info("レトリバー初期化開始")
            rag._init_retrievers()
            logger.info("レトリバー初期化完了")
            
            return {"status": "ok", "filename": file.filename, "ingested": 1}

    except Exception as e:
        import traceback
        logger.error(f"アップロードエラー: {str(e)}")
        logger.error(f"トレースバック: {traceback.format_exc()}")
        error_detail = f"エラー: {str(e)}\nトレースバック: {traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)
