# 北九州市ごみ分別チャットボット

LangChain + Ollama + ChromaDB を使用した RAG (Retrieval-Augmented Generation) チャットボットシステムです。

## ⚡ クイックスタート

```bash
# 1. プロジェクトディレクトリに移動
cd /path/to/kitakyushu-waste-chatbot

# 2. 自動セットアップ・起動
chmod +x start.sh
./start.sh

# 3. ブラウザでアクセス
# フロントエンド: http://localhost:8501
# API ドキュメント: http://localhost:8000/docs
```

## 📋 概要

このシステムは以下の技術スタックで構築されています：

- **LLM**: Ollama Llama 3.1 Swallow 8B (日本語対応)
- **Embedding**: kun432/cl-nagoya-ruri-large
- **ベクトルDB**: ChromaDB
- **バックエンド**: FastAPI
- **フロントエンド**: Streamlit
- **フレームワーク**: LangChain

## 🚀 セットアップ手順

### 1. 前提条件

- Python 3.8+
- Ollama がインストール済み
- GPU

### 2. Ollama モデルのインストール

```bash
# LLMモデルのダウンロード
ollama pull hf.co/mmnga/Llama-3.1-Swallow-8B-Instruct-v0.5-gguf

# Embeddingモデルのダウンロード
ollama pull nomic-embed-text

# 使いやすいエイリアス作成（オプション）
ollama cp hf.co/mmnga/Llama-3.1-Swallow-8B-Instruct-v0.5-gguf:latest llama3.1:8b-instruct

# インストール確認
ollama list
```

### 3. 依存関係のインストール

#### バックエンド
```bash
cd backend
pip install -r requirements.txt
```

#### フロントエンド
```bash
cd frontend
pip install -r requirements.txt
```

## 🎯 システム起動手順

### 🚀 簡単起動（推奨）

```bash
# プロジェクトルートで起動スクリプトを実行
chmod +x start.sh
./start.sh
```

### 🔧 手動起動

#### 1. Ollama サービスの起動

```bash
# Ollamaサービスが起動していない場合
ollama serve
```

#### 2. バックエンドAPI の起動

```bash
cd backend
python3 main.py
```

- サーバー起動URL: `http://localhost:8000`
- API ドキュメント: `http://localhost:8000/docs`

#### 3. フロントエンド UI の起動

```bash
cd frontend
streamlit run app.py --server.port 8501
```

- フロントエンド URL: `http://localhost:8501`

## 📊 API エンドポイント

### チャット機能

#### Bot Respond API (推奨)
```bash
# 新しいブロッキングモードエンドポイント
curl -X POST "http://localhost:8000/api/bot/respond" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "ペットボトルはどこに捨てればいいですか？"}'
```

#### Bot Streaming API (推奨)
```bash
# 新しいストリーミングモードエンドポイント
curl -N -X POST "http://localhost:8000/api/bot/stream" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"prompt": "空き缶の出し方を教えてください"}'
```

#### 従来のAPI（互換性維持）

##### Blocking モード
```bash
curl -X POST "http://localhost:8000/api/chat/blocking" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "ペットボトルはどこに捨てればいいですか？", "mode": "blocking"}'
```

##### Streaming モード
```bash
curl -X POST "http://localhost:8000/api/chat/streaming" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "空き缶の出し方を教えてください", "mode": "streaming"}'
```

### ファイルアップロード

#### CSVファイルのアップロード
```bash
curl -X POST "http://localhost:8000/api/upload" \
  -F "file=@data/sample.csv"
```

#### アップロードファイル一覧
```bash
curl -X GET "http://localhost:8000/api/files"
```

#### サンプルデータ生成
```bash
curl -X GET "http://localhost:8000/api/sample"
```

### システム監視

#### GPU使用状況
```bash
curl -X GET "http://localhost:8000/api/gpu-stats"
```

#### ヘルスチェック
```bash
curl -X GET "http://localhost:8000/api/health"
```

## 🗂️ プロジェクト構造

```
kitakyushu-waste-chatbot/
├── README.md                    # プロジェクト説明書
├── .gitignore                   # Git除外設定
├── docker-compose.yml           # Docker構成 (オプション)
├── requirements-definition.txt  # 要件定義書
├── start.sh                    # システム起動スクリプト
├── backend/                     # バックエンドAPI
│   ├── main.py                  # FastAPI メインアプリ
│   ├── requirements.txt         # Python依存関係
│   ├── api/                     # API エンドポイント
│   │   ├── __init__.py         # パッケージ初期化
│   │   ├── chat.py             # チャット機能 (blocking/streaming)
│   │   ├── upload.py           # ファイルアップロード
│   │   └── monitor.py          # システム監視
│   └── services/               # コアサービス
│       ├── __init__.py         # パッケージ初期化
│       ├── rag_service.py      # RAG機能 (ChromaDB + Ollama)
│       ├── logger.py           # ログ機能
│       ├── llm_service.py      # LLMサービス
│       └── gpu_moniter.py      # GPU監視
├── frontend/                   # フロントエンド UI
│   ├── app.py                  # Streamlit メインアプリ
│   └── requirements.txt        # Python依存関係
├── data/                       # データファイル
│   └── sample.csv              # サンプルごみ分別データ
├── chroma_db/                  # ChromaDB ベクトルデータベース
└── logs/                       # ログファイル
    └── gpu_monitor.log         # GPU監視ログ
```
│   └── sample.csv              # サンプルごみ分別データ
├── chroma_db/                  # ChromaDB データベース
└── logs/                       # ログファイル
    └── chat_logs.json          # チャットログ
```

## 📝 データ形式

### CSVファイル形式 (ナレッジベース)

```csv
品名,出し方,備考
ペットボトル,資源ごみ,キャップとラベルを外して出してください
空き缶,資源ごみ,中身を空にして軽く水洗いしてください
古紙,資源ごみ,ひもで十字に縛って出してください
生ごみ,燃えるごみ,水分をよく切って出してください
```

## 💡 使用方法

### 1. 初回セットアップ

1. システムを起動 (上記手順参照)
2. サンプルデータを生成・アップロード:
   ```bash
   # サンプルデータ生成
   curl -X GET "http://localhost:8000/api/sample"
   
   # サンプルデータアップロード
   curl -X POST "http://localhost:8000/api/upload" \
     -F "file=@data/sample.csv"
   ```

### 2. Web UI での使用

1. ブラウザで `http://localhost:8501` にアクセス
2. チャット画面で質問を入力
3. ファイルアップロード画面でCSVファイルをアップロード
4. GPU監視画面でシステム状況を確認

### 3. API での使用

```python
import requests

# チャット機能の使用例
response = requests.post(
    "http://localhost:8000/api/chat/blocking",
    json={"prompt": "ペットボトルの捨て方は？", "mode": "blocking"}
)
print(response.json())
```

## 🔧 トラブルシューティング

### よくある問題と解決方法

#### 1. Ollamaモデルが見つからない
```bash
# モデルリスト確認
ollama list

# 不足している場合は再ダウンロード
ollama pull hf.co/mmnga/Llama-3.1-Swallow-8B-Instruct-v0.5-gguf
ollama pull nomic-embed-text
```

#### 2. ChromaDBエラー
```bash
# データベースフォルダを削除して再初期化
rm -rf chroma_db/
# その後、サーバーを再起動
```

#### 3. ポート競合エラー
```bash
# 使用中のポートを確認
lsof -i :8000  # バックエンド
lsof -i :8501  # フロントエンド

# プロセス終了
kill -9 <PID>

# または全ての関連プロセスを停止
pkill -f "python3 main.py"
pkill -f "streamlit run"
```

#### 4. FastAPI非推奨警告
```bash
# main.pyが最新版に更新されていることを確認
# on_event は lifespan イベントハンドラーに変更済み
```

#### 5. 依存関係エラー
```bash
# 仮想環境での実行を推奨
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

## 📋 機能一覧

### ✅ 実装済み機能

- [x] RAG機能付きチャットボット
- [x] Blocking/Streaming 両モード対応
- [x] CSVファイルアップロード機能
- [x] Web UI (Streamlit)
- [x] REST API (FastAPI)
- [x] GPU使用量監視
- [x] JSONログ出力
- [x] 日本語対応 (Llama 3.1 Swallow)
- [x] レスポンス時間測定
- [x] ヘルスチェック機能

### 🎯 主要な動作確認済み例

```bash
# システム状況確認
curl -X GET "http://localhost:8000/api/health"
# 期待される回答: {"status":"ok","service":"kitakyushu-waste-chatbot"}

# ペットボトルについて質問
curl -X POST "http://localhost:8000/api/chat/blocking" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "ペットボトルはどこに捨てればいいですか？"}'

# 期待される回答:
# {"response":"ペットボトルは**資源ごみ**として、キャップとラベルを外して出してください。","mode":"blocking","latency":1.23,"timestamp":"2025-09-02T10:54:23.971362","context_found":true,"source_documents":1}
```

### 📊 システム監視

```bash
# 現在動作中のサーバー確認
curl -X GET "http://localhost:8000/api/health"      # バックエンド
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8501"  # フロントエンド (200が正常)

# GPU使用状況確認
curl -X GET "http://localhost:8000/api/gpu-stats"

# データベース情報確認（開発者向け）
curl -X GET "http://localhost:8000/api/database-info" || echo "※実装されていません"
```

## 🔗 関連リンク

- [FastAPI ドキュメント](https://fastapi.tiangolo.com/)
- [Streamlit ドキュメント](https://docs.streamlit.io/)
- [LangChain ドキュメント](https://python.langchain.com/)
- [Ollama ドキュメント](https://ollama.ai/)
- [ChromaDB ドキュメント](https://docs.trychroma.com/)

## 📞 サポート

問題が発生した場合は、以下を確認してください：

1. ログファイル: `logs/chat_logs.json`
2. システム状況: `http://localhost:8000/api/gpu-stats`
3. API状況: `http://localhost:8000/docs`

---

**注意**: 本番環境で使用する場合は、セキュリティ設定（CORS、認証など）を適切に設定してください。
