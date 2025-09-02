"""
北九州市ごみ分別チャットボット RAG サービス
- Embeddings: Ollama (bge-m3:latest)
- Vector DB: Chroma (./chroma_db に永続化)
- LLM: Ollama (Swallow v0.5 gguf)
"""

import os
import time
from datetime import datetime
from typing import List, Dict, Any, AsyncGenerator

import pandas as pd
import ollama
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

from backend.services.logger import setup_logger

# ===== 環境変数 / 既定値 =====
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3:latest")
LLM_MODEL   = os.getenv("LLM_MODEL", "hf.co/mmnga/Llama-3.1-Swallow-8B-Instruct-v0.5-gguf:latest")
CHROMA_DIR  = os.getenv("CHROMA_DIR", "./chroma_db")
DATA_DIR    = os.getenv("DATA_DIR", "./data")

class KitakyushuWasteRAGService:
    """RAGの初期化・CSV取り込み・検索・応答生成までまとめたサービス"""

    def __init__(self):
        self.logger = setup_logger(__name__)

        # Embedding
        self.embeddings = OllamaEmbeddings(model=EMBED_MODEL)

        # Vector DB (Chroma)
        os.makedirs(CHROMA_DIR, exist_ok=True)
        self.vectorstore = Chroma(
            persist_directory=CHROMA_DIR,
            embedding_function=self.embeddings
        )

        # 初回ロード（既存CSVがあれば取り込む）
        os.makedirs(DATA_DIR, exist_ok=True)
        self._load_csv_dir()

        self.logger.info(
            f"RAG ready | EMBED_MODEL={EMBED_MODEL} | LLM_MODEL={LLM_MODEL} | "
            f"CHROMA_DIR={CHROMA_DIR} | DATA_DIR={DATA_DIR}"
        )

    # ========= CSV 読み込み系 =========

    def _row_to_text(self, row: pd.Series) -> str:
        # 列名が異なるCSVでも動くよう、代表的なキーを併記
        item  = row.get("品名") or row.get("品目") or row.get("item") or ""
        how   = row.get("出し方") or row.get("処理方法") or row.get("how") or ""
        note  = row.get("備考") or row.get("注意") or row.get("note") or ""
        area  = row.get("エリア") or row.get("地区") or row.get("area") or ""

        lines = [
            f"品目: {item}",
            f"出し方: {how}",
            f"備考: {note}",
            f"エリア: {area}",
        ]
        return "\n".join(lines).strip()

    def add_csv(self, filepath: str) -> Dict[str, Any]:
        """単一CSVを読み込んでベクトル化"""
        if not os.path.exists(filepath):
            return {"success": False, "error": f"CSVが見つかりません: {filepath}"}

        try:
            df = pd.read_csv(filepath, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, encoding="cp932")

        docs: List[Document] = []
        for _, row in df.iterrows():
            text = self._row_to_text(row)
            if not text:
                continue
            docs.append(Document(page_content=text, metadata={"source": os.path.basename(filepath)}))

        if docs:
            self.vectorstore.add_documents(docs)
            self.logger.info(f"CSV取り込み: {filepath} | 文書数={len(docs)}")
            return {"success": True, "count": len(docs)}
        return {"success": True, "count": 0}

    def _load_csv_dir(self) -> None:
        """DATA_DIR 内のCSVをすべて取り込む（初期化時に一度実行）"""
        if not os.path.isdir(DATA_DIR):
            self.logger.warning(f"DATA_DIR が存在しません: {DATA_DIR}")
            return
        total = 0
        for fn in os.listdir(DATA_DIR):
            if fn.lower().endswith(".csv"):
                res = self.add_csv(os.path.join(DATA_DIR, fn))
                total += int(res.get("count", 0))
        self.logger.info(f"初期CSV取り込み完了: {total} 文書")

    # ========= 検索 & 生成 =========

    def similarity_search(self, query: str, k: int = 5) -> List[Document]:
        return self.vectorstore.similarity_search(query, k=k)

    def _format_docs(self, docs: List[Document]) -> str:
        if not docs:
            return "関連情報が見つかりませんでした。"
        return "\n\n".join(d.page_content for d in docs)

    def _call_llm(self, prompt: str) -> str:
        """Ollama LLM 呼び出し（blocking）"""
        res = ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_ctx": 4096},
        )
        return res["message"]["content"]

    def blocking_query(self, query: str, k: int = 5) -> Dict[str, Any]:
        """類似検索 → コンテキスト注入 → LLM で回答（blocking）"""
        t0 = time.time()
        docs = self.similarity_search(query, k=k)
        ctx = self._format_docs(docs)
        prompt = (
            "あなたは北九州市のごみ分別案内の専門AIです。"
            "以下の参照データの範囲内で、日本語で簡潔かつ正確に回答してください。"
            "\n\n質問:\n"
            f"{query}\n\n参照データ:\n{ctx}\n\n回答:"
        )
        try:
            answer = self._call_llm(prompt)
            return {
                "response": answer,
                "documents": len(docs),
                "latency": time.time() - t0,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"response": f"エラー: {e}", "documents": len(docs), "latency": time.time() - t0}

    async def streaming_query(self, query: str, k: int = 5) -> AsyncGenerator[str, None]:
        """類似検索 → LLM ストリーミング（SSE用）"""
        docs = self.similarity_search(query, k=k)
        ctx = self._format_docs(docs)
        prompt = (
            "あなたは北九州市のごみ分別案内の専門AIです。"
            "以下の参照データの範囲内で、日本語で簡潔かつ正確に回答してください。"
            f"\n\n質問:\n{query}\n\n参照データ:\n{ctx}\n\n回答:"
        )
        try:
            stream = ollama.chat(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                options={"temperature": 0.1, "num_ctx": 4096},
            )
            for chunk in stream:
                if chunk and chunk.get("message", {}).get("content"):
                    yield chunk["message"]["content"]
        except Exception as e:
            yield f"エラー: {e}"

# ======= シングルトン =======
_rag = None
def get_rag_service() -> KitakyushuWasteRAGService:
    global _rag
    if _rag is None:
        _rag = KitakyushuWasteRAGService()
    return _rag
