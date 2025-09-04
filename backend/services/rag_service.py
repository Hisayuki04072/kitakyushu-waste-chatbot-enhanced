"""
北九州市ごみ分別チャットボット RAG サービス（精度強化版 / エリアなし / 安定ストリーミング）

主な変更点：
- 召回後の語彙（品目）ベース再ランキングを追加して Top1 を厳選
- Top1 のレコードから "出し方" / "備考" を直接返す（LLM はフォールバック）
- エリア列（エリア/地区/area）を完全に廃止
- ストリーミングでは "出し方" → "備考" の順で即時送出（必要に応じて LLM に降格）
- Ollama の同期ストリームをバックグラウンドスレッドで取り出し、asyncio.Queue で非同期橋渡し
- ロギングを強化（選ばれたレコードやスコアの可視化）
"""

import os
import re
import json
import shutil
import time
import unicodedata
import asyncio
import threading
from datetime import datetime
from typing import List, Dict, Any, AsyncGenerator, Optional, Tuple

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

_DEF_PUNCTS = "?？。!！、\n \t\r"


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
    tmp = re.split(r'[はをにでがともへ]|[?？。!！、\n]', q, maxsplit=1)[0]
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


def _load_manifest() -> Optional[Dict[str, Any]]:
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
    """RAGの初期化・CSV取り込み・検索・応答生成（精度強化）"""

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

    # ========= CSV 読み込み（エリアは廃止） =========
    def _row_to_text(self, row: pd.Series) -> str:
        item  = row.get("品名") or row.get("品目") or row.get("item") or ""
        how   = row.get("出し方") or row.get("処理方法") or row.get("how") or ""
        note  = row.get("備考") or row.get("注意") or row.get("note") or ""
        return "\n".join([
            f"品目: {str(item).strip()}",
            f"出し方: {str(how).strip()}",
            f"備考: {str(note).strip()}",
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

    # ========= 検索（強化版：語彙リランク + 同義語） =========
    _SYNONYMS: Dict[str, List[str]] = {
        # 品目レベルの代表例（必要に応じて追記）
        "アルミ缶": ["アルミかん", "空き缶", "缶(アルミ)", "缶（アルミ）", "缶 アルミ", "アルミ 缶"],
        "スチール缶": ["スチールかん", "空き缶", "缶(スチール)", "缶（スチール）", "スチール 缶"],
        "ペットボトル": ["PET ボトル", "ペット ボトル", "ペット容器"],
    }

    def _parse_struct(self, text: str) -> Dict[str, str]:
        d = {"item": "", "how": "", "note": ""}
        for line in (text or "").splitlines():
            line = line.strip()
            if line.startswith("品目:"):
                d["item"] = line.split(":", 1)[1].strip()
            elif line.startswith("出し方:"):
                d["how"] = line.split(":", 1)[1].strip()
            elif line.startswith("備考:"):
                d["note"] = line.split(":", 1)[1].strip()
        return d

    def _lexical_score(self, query_item: str, doc_text: str) -> float:
        if not doc_text:
            return 0.0
        q = query_item.strip()
        if not q:
            return 0.0
        score = 0.0
        t = doc_text
        # 正確に "品目: <q>" を命中
        if f"品目: {q}" in t:
            score += 6.0
        # 同義語命中
        for syn in self._SYNONYMS.get(q, []):
            if syn and syn in t:
                score += 2.0
        # 任意位置に語が出現
        if q in t:
            score += 2.0
        # 出現回数の微加点
        score += t.count(q) * 0.2
        return score

    def _normalize_vec_score(self, raw: float) -> float:
        """Chroma の score はメトリクスにより大小関係が異なるので粗く正規化。
        - 0..1 ならそのまま（相関=高いほど良い想定）
        - 1..2.5 は cosine 距離とみなし 1/(1+raw)
        - それ以外はクリップ
        戻り値は [0,1]（大きいほど良い）。
        """
        if raw is None:
            return 0.0
        try:
            if 0.0 <= raw <= 1.0:
                return float(raw)
            if 0.0 <= raw <= 2.5:
                return 1.0 / (1.0 + float(raw))
        except Exception:
            pass
        return 0.0

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

    def _pick_best(self, query: str, k: int = DEFAULT_K) -> Optional[Tuple[Document, Dict[str, str], Dict[str, float]]]:
        """向量で召回 → 語彙スコアで再ランキング → Top1 を返す。
        戻り値: (doc, parsed_info, debug_scores)
        """
        k = max(K_MIN, min(k or DEFAULT_K, K_MAX))
        q_clean = clean_text(query)
        query_item = extract_item_like(q_clean)

        # with score が使えるなら活用
        cand_docs: List[Document] = []
        vec_scores: List[float] = []
        try:
            with_scores = self.vectorstore.similarity_search_with_score(q_clean, k=k)
            for d, sc in with_scores:
                cand_docs.append(d)
                vec_scores.append(float(sc))
        except Exception:
            # フォールバック
            cand_docs = self.similarity_search(q_clean, k=k)
            vec_scores = [None]*len(cand_docs)

        # 語彙スコア計算
        items = []
        for d, raw_sc in zip(cand_docs, vec_scores):
            txt = d.page_content or ""
            lex = self._lexical_score(query_item, txt)
            vec = self._normalize_vec_score(raw_sc)
            # 総合スコア（語彙寄り重み）
            total = 0.65 * lex + 0.35 * vec
            items.append((total, lex, vec, d))
        if not items:
            return None
        items.sort(key=lambda x: x[0], reverse=True)
        best_total, best_lex, best_vec, best_doc = items[0]
        info = self._parse_struct(best_doc.page_content or "")

        self.logger.info(
            "RAG pick | query=%s | item=%s | score_total=%.3f (lex=%.3f, vec=%.3f) | preview=%s",
            q_clean,
            info.get("item", ""),
            best_total,
            best_lex,
            best_vec,
            (best_doc.page_content or "").splitlines()[0][:50]
        )
        return best_doc, info, {"total": best_total, "lex": best_lex, "vec": best_vec}

    # ========= LLM 呼び出し =========
    def _call_llm(self, prompt: str) -> str:
        res = ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_ctx": 4096},
        )
        return (res.get("message", {}) or {}).get("content", "")

    # ========= ユーザーAPI（blocking） =========
    def blocking_query(self, query: str, k: int = DEFAULT_K) -> Dict[str, Any]:
        t0 = time.time()
        best = self._pick_best(query, k=k)
        if not best:
            msg = (
                "申し訳ございませんが、該当する情報がありません。"
                "北九州市のホームページでご確認いただくか、お住まいの区役所にお問い合わせください。"
            )
            return {"response": msg, "documents": 0, "latency": time.time() - t0, "timestamp": datetime.now().isoformat()}

        _, info, _scores = best
        how  = (info.get("how") or "").strip()
        note = (info.get("note") or "").strip()

        if how:
            ans = how if not note else f"{how}\n{note}"
            return {
                "response": ans,
                "documents": 1,
                "latency": time.time() - t0,
                "timestamp": datetime.now().isoformat(),
            }

        # 出し方が空の場合のみ LLM で整形（レアケース）
        ctx = (
            f"品目: {info.get('item','')}\n"
            f"出し方: {how}\n"
            f"備考: {note}"
        )
        prompt = (
            "あなたは北九州市のごみ分別案内の専門AIです。"
            "以下の単一レコードのみを根拠に、出し方→備考の順で1-2行で簡潔に回答してください。"
            "他の品目・一般論は出さない。\n\n対象レコード:\n" + ctx + "\n\n回答:"
        )
        try:
            answer = self._call_llm(prompt).strip()
        except Exception as e:
            answer = f"エラー: {e}"
        return {
            "response": answer,
            "documents": 1,
            "latency": time.time() - t0,
            "timestamp": datetime.now().isoformat(),
        }

    # ========= ユーザーAPI（streaming） =========
    async def streaming_query(self, query: str, k: int = DEFAULT_K) -> AsyncGenerator[str, None]:
        """できるだけ即時で要点を返すストリーミング。基本はレコード直出し。"""
        best = self._pick_best(query, k=k)
        if not best:
            yield (
                "申し訳ございませんが、該当する情報がありません。"
                "北九州市のホームページでご確認いただくか、お住まいの区役所にお問い合わせください。"
            )
            return

        _, info, _scores = best
        how  = (info.get("how") or "").strip()
        note = (info.get("note") or "").strip()

        # 1) まずは出し方を即時送出
        if how:
            yield how
            # 少しだけ譲る（SSE が即時 flush しやすいように）
            await asyncio.sleep(0)
            if note:
                yield "\n" + note
            return

        # 2) 出し方が空なら LLM で最小限整形（非同期ブリッジでブロック回避）
        ctx = (
            f"品目: {info.get('item','')}\n"
            f"出し方: {how}\n"
            f"備考: {note}"
        )
        prompt = (
            "あなたは北九州市のごみ分別案内の専門AIです。"
            "以下の単一レコードのみを根拠に、出し方→備考の順で1-2行で簡潔に回答してください。"
            "他の品目・一般論は出さない。\n\n対象レコード:\n" + ctx + "\n\n回答:"
        )

        # --- Ollama 同期ストリームをスレッドで吸い出し、Queue 経由で async へ ---
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=64)
        done = threading.Event()

        def producer():
            try:
                stream = ollama.chat(
                    model=LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    options={"temperature": 0.1, "num_ctx": 4096},
                )
                for chunk in stream:
                    if chunk.get("done"):
                        break
                    msg = chunk.get("message") or {}
                    piece = msg.get("content", "")
                    if piece:
                        # put_nowait だと満杯で例外になるので簡易リトライ
                        placed = False
                        while not placed and not done.is_set():
                            try:
                                # NB: 文字粒度が細かすぎるので軽くまとめる（ここではそのまま送り、上位でマイクロバッチ可）
                                queue.put_nowait(piece)
                                placed = True
                            except asyncio.QueueFull:
                                time.sleep(0.01)
            except Exception as e:
                try:
                    queue.put_nowait(f"エラー: {e}")
                except Exception:
                    pass
            finally:
                done.set()

        th = threading.Thread(target=producer, daemon=True)
        th.start()

        while not (done.is_set() and queue.empty()):
            try:
                piece = await asyncio.wait_for(queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if piece:
                yield piece
                await asyncio.sleep(0)

    # ======= シングルトン =======
_rag = None

def get_rag_service() -> KitakyushuWasteRAGService:
    global _rag
    if _rag is None:
        _rag = KitakyushuWasteRAGService()
    return _rag
