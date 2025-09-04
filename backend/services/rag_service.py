"""
北九州市ごみ分別チャットボット RAG サービス
- Embeddings: Ollama (bge-m3:latest)
- Vector DB: Chroma (./chroma_db に永続化)
- LLM: Ollama (Swallow v0.5 gguf)
"""

import os
import re
import json
import shutil
import time
import unicodedata
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

# 召回強度（環境変数で可調整）
DEFAULT_K   = int(os.getenv("RETRIEVER_K", "8"))
K_MAX       = int(os.getenv("RETRIEVER_K_MAX", "12"))
K_MIN       = int(os.getenv("RETRIEVER_K_MIN", "5"))

# ===== 軽量クレンジング =====
_ZERO_WIDTH_TRANS = dict.fromkeys([0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF], None)

def clean_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_ZERO_WIDTH_TRANS)
    return s.strip()

def strip_quotes_and_brackets(s: str) -> str:
    s = s.strip()
    s = re.sub(r'^[「『“"（(]+', '', s)
    s = re.sub(r'[」』”"）)]+$', '', s)
    return s.strip()

def extract_item_like(query: str) -> str:
    q = clean_text(query)
    m = re.search(r'「(.+?)」', q)
    if m:
        return strip_quotes_and_brackets(m.group(1))
    tmp = re.split(r'[はをにでがともへ]|[?？。!！、]', q, maxsplit=1)[0]
    tmp = strip_quotes_and_brackets(tmp)
    return tmp[:32].strip() if tmp else q

# ===== Embeddings ラッパ（BGE向けに query/passsage 前置詞を付ける）=====
class BGEInstructEmbeddings:
    """
    LangChain の埋め込みIF互換:
    - embed_documents(texts: List[str]) -> List[List[float]]
    - embed_query(text: str) -> List[float]
    """
    def __init__(self, model: str):
        self.inner = OllamaEmbeddings(model=model)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        texts2 = [f"passage: {clean_text(t)}" for t in texts]
        return self.inner.embed_documents(texts2)

    def embed_query(self, text: str) -> List[float]:
        return self.inner.embed_query(f"query: {clean_text(text)}")

# ===== Index manifest （埋め込みの一貫性チェック）=====
MANIFEST_FILE = "manifest.json"
MANIFEST_STRATEGY = "bge_query_passage_prefix_v1"

def _manifest_path() -> str:
    return os.path.join(CHROMA_DIR, MANIFEST_FILE)

def _load_manifest() -> Dict[str, Any] | None:
    try:
        with open(_manifest_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _write_manifest() -> None:
    os.makedirs(CHROMA_DIR, exist_ok=True)
    with open(_manifest_path(), "w", encoding="utf-8") as f:
        json.dump(
            {
                "embed_model": EMBED_MODEL,
                "strategy": MANIFEST_STRATEGY,
                "created_at": datetime.now().isoformat(),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

def _manifest_mismatch() -> bool:
    m = _load_manifest()
    if not m:
        # 以前のインデックスに manifest が無い場合、念のため再構築
        return True
    return not (
        m.get("embed_model") == EMBED_MODEL
        and m.get("strategy") == MANIFEST_STRATEGY
    )

# ===== 本体 =====
class KitakyushuWasteRAGService:
    """RAGの初期化・CSV取り込み・検索・応答生成"""

    def __init__(self):
        self.logger = setup_logger(__name__)

        # Embedding（BGE向け前置詞ラッパ使用）
        self.embeddings = BGEInstructEmbeddings(model=EMBED_MODEL)

        # 既存インデックスの健全性チェック（モデル/戦略が変わっていたら再作成）
        if os.path.isdir(CHROMA_DIR) and _manifest_mismatch():
            self.logger.warning("Embedding 設定が既存インデックスと不一致のため、再構築します。")
            shutil.rmtree(CHROMA_DIR, ignore_errors=True)

        # Vector DB (Chroma)
        os.makedirs(CHROMA_DIR, exist_ok=True)
        self.vectorstore = Chroma(
            persist_directory=CHROMA_DIR,
            embedding_function=self.embeddings
        )

        # 初回ロード（既存CSVがあれば取り込む）
        os.makedirs(DATA_DIR, exist_ok=True)
        self._load_csv_dir()
        _write_manifest()

        self.logger.info(
            f"RAG ready | EMBED_MODEL={EMBED_MODEL} | LLM_MODEL={LLM_MODEL} | "
            f"CHROMA_DIR={CHROMA_DIR} | DATA_DIR={DATA_DIR}"
        )

    # ========= CSV 読み込み =========
    def _row_to_text(self, row: pd.Series) -> str:
        item  = row.get("品名") or row.get("品目") or row.get("item") or ""
        how   = row.get("出し方") or row.get("処理方法") or row.get("how") or ""
        note  = row.get("備考") or row.get("注意") or row.get("note") or ""
        area  = row.get("エリア") or row.get("地区") or row.get("area") or ""
        return "\n".join([
            f"品目: {str(item).strip()}",
            f"出し方: {str(how).strip()}",
            f"備考: {str(note).strip()}",
            f"エリア: {str(area).strip()}",
        ]).strip()

    def add_csv(self, filepath: str) -> Dict[str, Any]:
        if not os.path.exists(filepath):
            return {"success": False, "error": f"CSVが見つかりません: {filepath}"}
        try:
            df = pd.read_csv(filepath, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, encoding="cp932")

        docs: List[Document] = []
        for _, row in df.iterrows():
            text = self._row_to_text(row)
            if text:
                docs.append(Document(page_content=text, metadata={"source": os.path.basename(filepath)}))
        if docs:
            self.vectorstore.add_documents(docs)
            self.logger.info(f"CSV取り込み: {filepath} | 文書数={len(docs)}")
            return {"success": True, "count": len(docs)}
        return {"success": True, "count": 0}

    def _load_csv_dir(self) -> None:
        total = 0
        for fn in os.listdir(DATA_DIR):
            if fn.lower().endswith(".csv"):
                res = self.add_csv(os.path.join(DATA_DIR, fn))
                total += int(res.get("count", 0))
        self.logger.info(f"初期CSV取り込み完了: {total} 文書")

    # ========= 検索（強化版） =========
    def _format_docs(self, docs: List[Document], limit_each: int = 320, max_docs: int = 4) -> str:
        if not docs:
            return "関連情報が見つかりませんでした。"
        chunks = []
        for i, d in enumerate(docs[:max_docs], start=1):
            txt = (d.page_content or "").strip()
            if len(txt) > limit_each:
                txt = txt[:limit_each] + "…"
            chunks.append(f"[候補{i}]\n{txt}")
        return "\n\n".join(chunks)

    def similarity_search(self, query: str, k: int = DEFAULT_K) -> List[Document]:
        k = max(K_MIN, min(k or DEFAULT_K, K_MAX))
        q_clean = clean_text(query)

        # 1) 通常検索
        try:
            docs = self.vectorstore.similarity_search(q_clean, k=k)
        except Exception as e:
            self.logger.warning(f"similarity_search failed (normal): {e}")
            docs = []

        def poor(dlist: List[Document]) -> bool:
            if not dlist:
                return True
            heads = sum(1 for d in dlist if "品目:" in (d.page_content or ""))
            return heads < max(1, len(dlist)//3)

        if not poor(docs):
            return docs

        # 2) MMR（多様性）
        try:
            docs_mmr = self.vectorstore.max_marginal_relevance_search(q_clean, k=k, fetch_k=max(k*2, 8))
        except Exception as e:
            self.logger.warning(f"MMR search failed: {e}")
            docs_mmr = []
        if not poor(docs_mmr):
            return docs_mmr

        # 3) 品目抽出クエリで再検索（通常→MMR）
        item_q = extract_item_like(q_clean)
        try:
            docs2 = self.vectorstore.similarity_search(item_q, k=k)
        except Exception as e:
            self.logger.warning(f"similarity_search failed (item): {e}")
            docs2 = []
        if not poor(docs2):
            return docs2

        try:
            docs2_mmr = self.vectorstore.max_marginal_relevance_search(item_q, k=k, fetch_k=max(k*2, 8))
        except Exception as e:
            self.logger.warning(f"MMR search failed (item): {e}")
            docs2_mmr = []
        return docs2_mmr

    # ========= LLM 呼び出し =========
    def _call_llm(self, prompt: str) -> str:
        res = ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_ctx": 4096},
        )
        return (res.get("message", {}) or {}).get("content", "")

    # ========= ユーザーAPI =========
    def blocking_query(self, query: str, k: int = DEFAULT_K) -> Dict[str, Any]:
        t0 = time.time()
        docs = self.similarity_search(query, k=k)
        ctx = self._format_docs(docs)

        prompt = (
            "あなたは北九州市のごみ分別案内の専門AIです。"
            "以下の参照データの範囲内で、日本語で簡潔かつ正確に回答してください。"
            "最優先で「出し方」を特定して、そのままの表記で出力する。次に「備考」があれば補足する。"
            "重要なルール:"
            "1. 質問された品目に関連する情報のみを回答してください（関係ない品目の情報は含めないでください）"
            "2. データベースに該当する情報がない場合は「申し訳ございませんが、該当する情報がありません。北九州市のホームページでご確認いただくか、お住まいの区役所にお問い合わせください。」と回答してください"
            "3. 回答は簡潔で分かりやすく、出し方と備考を含めてください"
            "4. 推測や一般的なアドバイスは避け、データに基づいた正確な情報のみを提供してください"
            "5. 複数の関連品目がある場合は、質問に最も関連するもののみを優先して回答してください"
            "\n\n質問:\n"
            f"{clean_text(query)}\n\n参照データ:\n{ctx}\n\n回答:"
        )
        try:
            answer = self._call_llm(prompt).strip()
            return {
                "response": answer,
                "documents": len(docs),
                "latency": time.time() - t0,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"response": f"エラー: {e}", "documents": len(docs), "latency": time.time() - t0}

    async def streaming_query(self, query: str, k: int = DEFAULT_K) -> AsyncGenerator[str, None]:
        docs = self.similarity_search(query, k=k)
        ctx = self._format_docs(docs)

        prompt = (
            "あなたは北九州市のごみ分別案内の専門AIです。"
            "以下の参照データの範囲内で、日本語で簡潔かつ正確に回答してください。"
            "最優先で「出し方」を特定して、そのままの表記で出力する。次に「備考」があれば補足する。"
            "重要なルール:"
            "1. 質問された品目に関連する情報のみを回答してください（関係ない品目の情報は含めないでください）"
            "2. データベースに該当する情報がない場合は「申し訳ございませんが、該当する情報がありません。北九州市のホームページでご確認いただくか、お住まいの区役所にお問い合わせください。」と回答してください"
            "3. 回答は簡潔で分かりやすく、出し方と備考を含めてください"
            "4. 推測や一般的なアドバイスは避け、データに基づいた正確な情報のみを提供してください"
            "5. 複数の関連品目がある場合は、質問に最も関連するもののみを優先して回答してください"
            f"\n\n質問:\n{clean_text(query)}\n\n参照データ:\n{ctx}\n\n回答:"
        )
        try:
            stream = ollama.chat(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                options={"temperature": 0.1, "num_ctx": 4096},
            )
            for chunk in stream:
                piece = (chunk.get("message", {}) or {}).get("content", "")
                if piece:
                    yield piece
        except Exception as e:
            yield f"エラー: {e}"

# ======= シングルトン =======
_rag = None
def get_rag_service() -> KitakyushuWasteRAGService:
    global _rag
    if _rag is None:
        _rag = KitakyushuWasteRAGService()
    return _rag
