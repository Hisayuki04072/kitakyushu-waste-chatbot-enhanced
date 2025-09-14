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
import asyncio

import pandas as pd
import ollama
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever

from .logger import setup_logger

# ===== 環境変数 / 既定値 =====
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")
LLM_MODEL   = os.getenv("LLM_MODEL", "hf.co/mmnga/Llama-3.1-Swallow-8B-Instruct-v0.5-gguf:latest")
CHROMA_DIR  = os.getenv("CHROMA_DIR", "./chroma_db")
DATA_DIR    = os.getenv("DATA_DIR", "./data")

# 召回強度（環境変数で可調整）
DEFAULT_K   = int(os.getenv("RETRIEVER_K", "10"))
K_MAX       = int(os.getenv("RETRIEVER_K_MAX", "12"))
K_MIN       = int(os.getenv("RETRIEVER_K_MIN", "5"))

# ===== 軽量クレンジング =====
_ZERO_WIDTH_TRANS = dict.fromkeys([0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF], None)

def clean_text(text: str) -> str:
    """テキストをクリーンアップ"""
    if not text:
        return ""
    # Unicode正規化とゼロ幅文字の除去
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_ZERO_WIDTH_TRANS)
    # 余分な空白を除去
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_item_like(query: str) -> str:
    """クエリからアイテム名を抽出"""
    if not query:
        return ""
    
    # 「〜の捨て方」「〜はどう」などのパターンからアイテム名を抽出
    patterns = [
        r'(.+?)の(?:捨て方|分別|処理|出し方)',
        r'(.+?)は(?:どう|どのように|どこに)',
        r'(.+?)を(?:捨てる|分別|処理)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            return clean_text(match.group(1))
    
    # パターンにマッチしない場合は、クエリ全体をアイテム名として扱う
    return clean_text(query)

# ===== 表記揺れ・同義語辞書 =====
SYNONYMS_MAP = {
    # アルミ関連
    "アルミ缶": ["アルミかん", "アルミカン", "あるみかん", "あるみ缶"],
    "アルミかん": ["アルミ缶", "アルミカン", "あるみかん", "あるみ缶"],
    
    # カタカナ・ひらがな揺れ
    "ペットボトル": ["ペット", "ぺっと", "ペットボトル"],
    "プラスチック": ["プラ", "ぷら"],
    
    # 略語・省略形
    "テレビ": ["TV", "tv", "ティーブイ", "てれび"],
    "エアコン": ["エアーコンディショナー", "クーラー", "えあこん"],
    
    # カン・びん関連
    "缶": ["かん", "カン"],
    "瓶": ["びん", "ビン", "ガラス瓶"],
    
    # 家電製品
    "冷蔵庫": ["れいぞうこ", "冷凍庫"],
    "洗濯機": ["せんたくき", "洗濯機"],
    
    # 一般的な表記揺れ
    "携帯電話": ["携帯", "スマホ", "スマートフォン", "けいたい"],
    "乾電池": ["電池", "でんち", "バッテリー"],
}

def expand_query_with_synonyms(query: str) -> List[str]:
    """
    クエリを同義語で拡張
    """
    queries = [query]
    query_lower = query.lower()
    
    # 完全一致での同義語展開
    for key, synonyms in SYNONYMS_MAP.items():
        if key in query:
            for synonym in synonyms:
                new_query = query.replace(key, synonym)
                if new_query not in queries:
                    queries.append(new_query)
        
        # 同義語からキーへの展開
        for synonym in synonyms:
            if synonym in query:
                new_query = query.replace(synonym, key)
                if new_query not in queries:
                    queries.append(new_query)
    
    return queries

# ===== 本体 =====
class KitakyushuWasteRAGService:
    """RAGの初期化・CSV取り込み・検索・応答生成"""

    def __init__(self):
        self.logger = setup_logger(__name__)

        # ChromaDBのtelemetryを完全に無効化
        os.environ["ANONYMIZED_TELEMETRY"] = "False"
        os.environ["CHROMA_TELEMETRY"] = "False"
        os.environ["POSTHOG_DISABLED"] = "True"
        os.environ["CHROMA_DISABLE_TELEMETRY"] = "True"
        os.environ["DO_NOT_TRACK"] = "1"
        # 追加のtelemetry無効化設定
        os.environ["CHROMA_ANALYTICS_DISABLED"] = "True"
        os.environ["CHROMA_DISABLE_ANALYTICS"] = "True"
        
        # PostHogのテレメトリを完全無効化
        try:
            import chromadb.telemetry
            if hasattr(chromadb.telemetry, 'posthog'):
                chromadb.telemetry.posthog.Posthog = lambda *args, **kwargs: None
        except (ImportError, AttributeError):
            pass

        self.embeddings = OllamaEmbeddings(model=EMBED_MODEL)

        # 永続化ディレクトリが存在する場合は削除（重複防止とメモリベースに移行）
        if os.path.isdir(CHROMA_DIR):
            self.logger.info("既存の永続化ChromaDBを削除してインメモリに移行します。")
            shutil.rmtree(CHROMA_DIR, ignore_errors=True)
        
        # 重複防止のためのドキュメント管理
        self.document_ids = set()  # 重複防止用のドキュメントIDセット
        
        try:
            # ChromaDBをインメモリで初期化（永続化無効）
            self.vectorstore = Chroma(
                embedding_function=self.embeddings
            )
            self.logger.info("ChromaDBをインメモリモードで初期化しました（永続化無効）")
        except Exception as e:
            self.logger.error(f"ChromaDB初期化エラー: {e}")
            # 再試行
            self.vectorstore = Chroma(
                embedding_function=self.embeddings
            )

        # BM25とアンサンブルレトリバーの初期化
        self.bm25_retriever = None
        self.ensemble_retriever = None

        os.makedirs(DATA_DIR, exist_ok=True)
        self._load_csv_dir()
        self._init_retrievers()

        self.logger.info(
            f"RAG ready (インメモリモード) | EMBED_MODEL={EMBED_MODEL} | LLM_MODEL={LLM_MODEL} | "
            f"DATA_DIR={DATA_DIR} | 重複防止機能=有効"
        )

    def clear_all_data(self) -> Dict[str, Any]:
        """全てのデータをクリアする（インメモリなので再初期化）"""
        try:
            # ドキュメントIDセットをクリア
            self.document_ids.clear()
            
            # ベクトルストアを再初期化
            self.vectorstore = Chroma(
                embedding_function=self.embeddings
            )
            
            # レトリバーもリセット
            self.bm25_retriever = None
            self.ensemble_retriever = None
            
            self.logger.info("全データをクリアしました（インメモリモード）")
            return {"success": True, "message": "全データをクリアしました"}
        except Exception as e:
            self.logger.error(f"データクリアエラー: {e}")
            return {"success": False, "error": str(e)}

    def cleanup_on_shutdown(self) -> None:
        """サーバー終了時のクリーンアップ処理"""
        try:
            self.logger.info("サーバー終了時のクリーンアップを開始します...")
            
            # ベクトルデータベースを初期化
            self.document_ids.clear()
            self.vectorstore = Chroma(embedding_function=self.embeddings)
            self.bm25_retriever = None
            self.ensemble_retriever = None
            self.logger.info("ベクトルデータベースを初期化しました")
            
            # ChromaDBディレクトリが存在する場合は削除
            if os.path.isdir(CHROMA_DIR):
                shutil.rmtree(CHROMA_DIR, ignore_errors=True)
                self.logger.info(f"ChromaDBディレクトリを削除しました: {CHROMA_DIR}")
            
            # CSVファイルを削除
            if os.path.isdir(DATA_DIR):
                csv_files = [f for f in os.listdir(DATA_DIR) if f.lower().endswith('.csv')]
                for csv_file in csv_files:
                    try:
                        csv_path = os.path.join(DATA_DIR, csv_file)
                        os.remove(csv_path)
                        self.logger.info(f"CSVファイルを削除しました: {csv_file}")
                    except Exception as e:
                        self.logger.warning(f"CSVファイル削除エラー {csv_file}: {e}")
                
                # dataディレクトリが空の場合は削除
                try:
                    if not os.listdir(DATA_DIR):
                        os.rmdir(DATA_DIR)
                        self.logger.info(f"空のdataディレクトリを削除しました: {DATA_DIR}")
                except Exception as e:
                    self.logger.warning(f"dataディレクトリ削除エラー: {e}")
            
            self.logger.info("サーバー終了時のクリーンアップが完了しました")
            
        except Exception as e:
            self.logger.error(f"クリーンアップエラー: {e}")
            import traceback
            self.logger.error(f"トレースバック: {traceback.format_exc()}")

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

    def _generate_document_id(self, text: str, source: str) -> str:
        """ドキュメントの一意IDを生成（重複防止用）"""
        import hashlib
        content_hash = hashlib.md5((text + source).encode('utf-8')).hexdigest()
        return f"{source}_{content_hash}"

    def add_csv(self, filepath: str) -> Dict[str, Any]:
        if not os.path.exists(filepath):
            return {"success": False, "error": f"CSVが見つかりません: {filepath}"}
        try:
            df = pd.read_csv(filepath, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, encoding="cp932")

        docs: List[Document] = []
        duplicates = 0
        
        for _, row in df.iterrows():
            text = self._row_to_text(row)
            if text:
                source = os.path.basename(filepath)
                doc_id = self._generate_document_id(text, source)
                
                # 重複チェック
                if doc_id in self.document_ids:
                    duplicates += 1
                    continue
                
                # 新しいドキュメントとして追加
                self.document_ids.add(doc_id)
                docs.append(Document(
                    page_content=text, 
                    metadata={"source": source, "doc_id": doc_id}
                ))
        
        if docs:
            self.vectorstore.add_documents(docs)
            # CSVが追加されたらレトリバーを再初期化
            self._init_retrievers()
            self.logger.info(f"CSV取り込み完了: {filepath} | 新規文書数={len(docs)} | 重複スキップ={duplicates} | ハイブリッド検索を再初期化")
            return {"success": True, "count": len(docs), "duplicates": duplicates}
        
        if duplicates > 0:
            self.logger.info(f"CSV処理完了: {filepath} | 全て重複データでした | 重複スキップ={duplicates}")
            return {"success": True, "count": 0, "duplicates": duplicates}
        
        return {"success": True, "count": 0}

    def _load_csv_dir(self) -> None:
        total = 0
        for fn in os.listdir(DATA_DIR):
            if fn.lower().endswith(".csv"):
                res = self.add_csv(os.path.join(DATA_DIR, fn))
                total += int(res.get("count", 0))
        self.logger.info(f"初期CSV取り込み完了: {total} 文書")

    def _init_retrievers(self) -> None:
        """BM25とアンサンブルレトリバーを初期化"""
        try:
            # ベクトルストアから全ドキュメントを取得
            all_docs = self.vectorstore.get()
            if all_docs and all_docs.get('documents'):
                # Documentオブジェクトのリストを作成
                documents = [Document(page_content=doc) for doc in all_docs['documents']]
                
                # BM25レトリバーを初期化
                if len(documents) > 0:
                    self.bm25_retriever = BM25Retriever.from_documents(documents)
                    self.bm25_retriever.k = DEFAULT_K
                    
                    # ベクトルストアのレトリバー
                    vector_retriever = self.vectorstore.as_retriever(search_kwargs={"k": DEFAULT_K})
                    
                    # アンサンブルレトリバー（BGE-M3ベクトル検索とBM25を組み合わせ）
                    # 重み: BGE-M3=0.6, BM25=0.4 (セマンティック検索を重視)
                    self.ensemble_retriever = EnsembleRetriever(
                        retrievers=[vector_retriever, self.bm25_retriever],
                        weights=[0.6, 0.4]  # BGE-M3を重視したハイブリッド検索
                    )
                    
                    self.logger.info(f"ハイブリッド検索を初期化しました (BGE-M3 + BM25)。ドキュメント数: {len(documents)}")
                    self.logger.info(f"重み設定 - BGE-M3: 0.6, BM25: 0.4")
                else:
                    self.logger.warning("ドキュメントが見つからないため、BM25レトリバーは初期化されませんでした。")
            else:
                self.logger.warning("ベクトルストアにドキュメントがないため、BM25レトリバーは初期化されませんでした。")
                # 空の場合でもレトリバーを後で再初期化できるようにNoneを設定
                self.bm25_retriever = None
                self.ensemble_retriever = None
        except Exception as e:
            self.logger.error(f"レトリバー初期化エラー: {e}")
            self.bm25_retriever = None
            self.ensemble_retriever = None

    # ========= 検索（強化版） =========
    def _format_docs(self, docs: List[Document], limit_each: int = 320, max_docs: int = 8) -> str:
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
        
        # 同義語拡張クエリを生成
        expanded_queries = expand_query_with_synonyms(q_clean)
        self.logger.info(f"Expanded queries: {expanded_queries}")
        
        item_q = extract_item_like(q_clean)
        
        # ハイブリッド検索（BGE-M3 + BM25）を実行
        all_docs = []
        
        # アンサンブルレトリバーが利用可能な場合はそれを使用（メイン検索）
        if self.ensemble_retriever is not None:
            for expanded_query in expanded_queries:
                try:
                    docs = self.ensemble_retriever.get_relevant_documents(expanded_query)
                    all_docs.extend(docs)
                    self.logger.info(f"Hybrid search (BGE-M3 + BM25) returned {len(docs)} documents for query: {expanded_query}")
                except Exception as e:
                    self.logger.warning(f"Ensemble retriever failed for '{expanded_query}': {e}")
                    # フォールバックとしてベクトル検索のみを実行
                    try:
                        docs_fallback = self.vectorstore.similarity_search(expanded_query, k=k)
                        all_docs.extend(docs_fallback)
                        self.logger.info(f"Fallback vector search returned {len(docs_fallback)} documents")
                    except Exception as e2:
                        self.logger.error(f"Fallback vector search also failed: {e2}")
        else:
            self.logger.warning("Ensemble retriever not available, using vector search only")
            # アンサンブルレトリバーが利用できない場合はベクトル検索のみ
            for expanded_query in expanded_queries:
                try:
                    docs_main = self.vectorstore.similarity_search(expanded_query, k=k)
                    all_docs.extend(docs_main)
                    self.logger.info(f"Vector-only search returned {len(docs_main)} documents for query: {expanded_query}")
                except Exception as e:
                    self.logger.warning(f"Vector search failed for '{expanded_query}': {e}")

        def item_match_score(txt: str, item: str) -> int:
            if not txt:
                return 0
            m = re.search(r"品目:\s*(.+)", txt)
            name = (m.group(1) if m else "").strip()
            if not name:
                return 0
            n1 = clean_text(name)
            n2 = clean_text(item)
            
            # 同義語も考慮したマッチング
            if n1 == n2:
                return 3
            
            # 同義語チェック
            for key, synonyms in SYNONYMS_MAP.items():
                if (n1 == key and n2 in synonyms) or (n2 == key and n1 in synonyms):
                    return 2
                if n1 in synonyms and n2 in synonyms:
                    return 2
            
            return 1 if (n2 and (n2 in n1 or n1 in n2)) else 0

        def rerank_by_item(docs, item):
            return sorted(docs, key=lambda d: item_match_score((d.page_content or ""), item), reverse=True)

        def poor(dlist: List[Document], item_hint: str) -> bool:
            if not dlist:
                return True
            heads = sum(1 for d in dlist if "品目:" in (d.page_content or ""))
            has_item = any(item_match_score((d.page_content or ""), item_hint) > 0 for d in dlist)
            return heads < max(1, len(dlist)//3) or not has_item

        def merge_dedup(lists):
            seen = set()
            out = []
            for lst in lists:
                for d in lst or []:
                    key = ((d.page_content or "").strip(), json.dumps(getattr(d, "metadata", {}), ensure_ascii=False, sort_keys=True))
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(d)
            return out

        def merge_dedup(lists):
            seen = set()
            out = []
            for lst in lists:
                for d in lst or []:
                    key = ((d.page_content or "").strip(), json.dumps(getattr(d, "metadata", {}), ensure_ascii=False, sort_keys=True))
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(d)
            return out

        # 重複を除去
        all_docs = merge_dedup([all_docs])
        all_docs = rerank_by_item(all_docs, item_q)
        
        # 十分な結果が得られた場合はここで終了
        if not poor(all_docs, item_q) and len(all_docs) >= k//2:
            self.logger.info(f"Hybrid search completed successfully with {len(all_docs[:k])} documents")
            return all_docs[:k]

        # 追加検索（アイテム名での検索）- ハイブリッド検索で実行
        if item_q:
            # アイテム名も同義語拡張
            expanded_items = expand_query_with_synonyms(item_q)
            for expanded_item in expanded_items:
                if self.ensemble_retriever is not None:
                    try:
                        docs_item = self.ensemble_retriever.get_relevant_documents(expanded_item)
                        all_docs.extend(docs_item)
                        self.logger.info(f"Hybrid item search returned {len(docs_item)} documents for: {expanded_item}")
                    except Exception as e:
                        self.logger.warning(f"Hybrid item search failed for '{expanded_item}': {e}")
                        # フォールバック
                        try:
                            docs_item = self.vectorstore.similarity_search(expanded_item, k=k)
                            all_docs.extend(docs_item)
                        except Exception as e2:
                            self.logger.warning(f"Fallback item search failed for '{expanded_item}': {e2}")
                else:
                    try:
                        docs_item = self.vectorstore.similarity_search(expanded_item, k=k)
                        all_docs.extend(docs_item)
                    except Exception as e:
                        self.logger.warning(f"Vector item search failed for '{expanded_item}': {e}")

        # 最終的な重複除去とランキング
        final_docs = merge_dedup([all_docs])
        final_docs = rerank_by_item(final_docs, item_q)
        
        self.logger.info(f"Final hybrid search result: {len(final_docs[:k])} documents")
        return final_docs[:k]

    def format_documents(self, docs: List[Document], limit_each: int = 150) -> str:
        return self._format_docs(docs, limit_each)

    def get_search_info(self) -> Dict[str, Any]:
        """検索システムの情報を返す"""
        info = {
            "embedding_model": EMBED_MODEL,
            "vector_store": "ChromaDB (In-Memory)",
            "persistence": "Disabled",
            "deduplication": "Enabled",
            "bm25_available": self.bm25_retriever is not None,
            "hybrid_search_available": self.ensemble_retriever is not None,
            "total_documents": 0,
            "unique_document_ids": len(self.document_ids)
        }
        
        try:
            all_docs = self.vectorstore.get()
            if all_docs and all_docs.get('documents'):
                info["total_documents"] = len(all_docs['documents'])
        except Exception as e:
            self.logger.warning(f"Failed to get document count: {e}")
        
        if info["hybrid_search_available"]:
            info["search_type"] = "Hybrid (BGE-M3 + BM25)"
            info["weights"] = {"BGE-M3": 0.6, "BM25": 0.4}
        elif info["bm25_available"]:
            info["search_type"] = "BM25 only"
        else:
            info["search_type"] = "Vector (BGE-M3) only"
        
        return info

    # ========= LLM 呼び出し =========
    def _call_llm(self, prompt: str) -> str:
        try:
            self.logger.info(f"LLM呼び出し開始 - モデル: {LLM_MODEL}")
            res = ollama.chat(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1, "num_ctx": 4096},
            )
            response = (res.get("message", {}) or {}).get("content", "")
            self.logger.info(f"LLM呼び出し成功 - レスポンス長: {len(response)}")
            return response
        except Exception as e:
            self.logger.error(f"LLM呼び出しエラー: {e}")
            self.logger.error(f"使用モデル: {LLM_MODEL}")
            # フォールバックとしてllama3.1:8bを試す
            try:
                self.logger.info("フォールバックモデル llama3.1:8b を試行")
                res = ollama.chat(
                    model="llama3.1:8b",
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.1, "num_ctx": 4096},
                )
                response = (res.get("message", {}) or {}).get("content", "")
                self.logger.info(f"フォールバックモデル成功 - レスポンス長: {len(response)}")
                return response
            except Exception as fallback_error:
                self.logger.error(f"フォールバックモデルもエラー: {fallback_error}")
                return f"申し訳ございませんが、現在AIサービスが利用できません。しばらく後でお試しください。エラー: {str(e)}"

    # ========= ユーザーAPI =========
    def blocking_query(self, query: str, k: int = DEFAULT_K) -> Dict[str, Any]:
        t0 = time.time()
        try:
            self.logger.info(f"質問受信: {query}")
            docs = self.similarity_search(query, k=k)
            self.logger.info(f"検索結果: {len(docs)}件のドキュメントを取得")
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
            
            answer = self._call_llm(prompt).strip()
            result = {
                "response": answer,
                "documents": len(docs),
                "latency": time.time() - t0,
                "timestamp": datetime.now().isoformat(),
            }
            self.logger.info(f"回答生成完了 - 処理時間: {result['latency']:.2f}秒")
            return result
            
        except Exception as e:
            self.logger.error(f"blocking_query エラー: {e}")
            import traceback
            self.logger.error(f"トレースバック: {traceback.format_exc()}")
            return {
                "response": f"申し訳ございませんが、処理中にエラーが発生しました。しばらく後でお試しください。",
                "documents": 0,
                "latency": time.time() - t0,
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }

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
                # 正确处理流结束信号
                if chunk.get("done"):
                    break
                msg = chunk.get("message") or {}
                content = msg.get("content", "")
                if content:
                    yield content
        except Exception as e:
            yield f"エラー: {e}"
# ======= シングルトン =======
_rag = None
def get_rag_service() -> KitakyushuWasteRAGService:
    global _rag
    if _rag is None:
        try:
            _rag = KitakyushuWasteRAGService()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"RAGサービス初期化エラー: {e}")
            logger.error(f"トレースバック: {__import__('traceback').format_exc()}")
            raise e
    return _rag
