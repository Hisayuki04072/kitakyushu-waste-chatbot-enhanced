# 北九州市ごみ分別チャットボット

本プロジェクトは **FastAPI + LangChain + Ollama + Streamlit** を活用した「ごみ分別チャットボット」です。  
バックエンドでは **RAG（検索拡張生成）** を用い、CSV ファイルを知識ベースとして登録できます。  
フロントエンドは **Streamlit** により、Web ブラウザから簡単に操作できます。  

---

## ✨ 主な機能

- 📂 **CSV アップロード機能**  
  ごみ分別に関する CSV データをアップロードし、知識ベースとして利用可能。  

- 🤖 **大規模言語モデル（LLM）**  
  サーバーにインストールされた **Ollama** のモデル（例：`llama3`、`nomic-embed-text`）を利用。  

- 🔍 **RAG による回答生成**  
  質問に対して、知識ベースを参照した自然な日本語で回答。  

- 📊 **GPU 監視 API**  
  サーバーの GPU 使用状況を API 経由で確認可能。  

- 🖥 **Web UI**  
  Streamlit による簡単なチャット画面を提供。  

---

## 📦 セットアップ手順

### 1. リポジトリをクローン
```bash
git clone <your-repo-url>
cd kitakyushu-waste-chatbot-main
2. Python 環境の準備


conda create -n chatbot python=3.11 -y
conda activate chatbot
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt
3. Ollama の準備
サーバーに Ollama をインストールし、以下のモデルを用意してください：

llama3 （対話用モデル）

nomic-embed-text （埋め込みモデル）

確認：



ollama list
4. バックエンド起動


cd backend
uvicorn main:app --host 0.0.0.0 --port 8080
API が起動したら次の URL で確認できます：

cpp

http://<サーバーIP>:8080
5. フロントエンド起動


cd frontend
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
Web UI にアクセス：

cpp

http://<サーバーIP>:8501
📤 CSV アップロード例


curl -F "file=@/home/chunjie/kitakyushu-waste-chatbot-main/data/test.csv" \
http://127.0.0.1:8080/api/upload
🩺 API チェック
ヘルスチェック



curl http://127.0.0.1:8080/health
GPU モニタリング


复制代码
curl http://127.0.0.1:8080/api/monitor/gpu
🚀 利用イメージ
CSV をアップロードして知識ベースを登録

フロントエンドで質問（例：「アルミ缶はどう捨てればいいですか？」）

LLM が CSV 知識ベースを参照して回答



