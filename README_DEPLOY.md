# 北九州市ごみ分別チャットボット

高機能なRAG（Retrieval-Augmented Generation）ベースのチャットボットシステムです。

## 🚀 デプロイ方法

### 前提条件

- Docker & Docker Compose がインストールされていること
- GPU使用の場合: NVIDIA Container Toolkit がインストールされていること
- 8GB以上のRAM推奨

### 1. クイックデプロイ

```bash
# リポジトリをクローン
git clone https://github.com/Hisayuki04072/kitakyushu-waste-chatbot-enhanced.git
cd kitakyushu-waste-chatbot-enhanced

# デプロイ実行
./deploy.sh
```

### 2. 手動デプロイ

```bash
# 1. SSL証明書生成
./generate_ssl.sh

# 2. 環境変数設定
cp .env.example .env
# 必要に応じて .env を編集

# 3. コンテナ起動
docker-compose -f docker-compose.prod.yml up -d

# 4. ログ確認
docker-compose -f docker-compose.prod.yml logs -f
```

### 3. アクセス方法

- **メインアプリ**: https://localhost (推奨)
- **HTTP**: http://localhost (HTTPSにリダイレクト)
- **フロントエンド直接**: http://localhost:8501
- **バックエンドAPI**: http://localhost:8000

## 📊 システム構成

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    Nginx        │    │   Streamlit     │    │   FastAPI       │
│  (Reverse       │────│   Frontend      │────│   Backend       │
│   Proxy)        │    │   :8501         │    │   :8000         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                                              │
         │                                              │
         └─────────────── HTTPS/HTTP ─────────────────────┘
                                │
                    ┌─────────────────┐
                    │    Ollama       │
                    │   LLM Server    │
                    │   :11434        │
                    └─────────────────┘
```

## 🛠️ 主要機能

### フロントエンド機能
- 📱 レスポンシブなWebUI
- 🚀 リアルタイムストリーミング応答
- 📄 CSVファイルアップロード・管理
- 📊 システム監視ダッシュボード
- 🌏 多言語対応（日本語・英語）

### バックエンド機能
- 🤖 Llama-3.1-Swallow-8B による日本語特化LLM
- 🔍 BGE-M3 + BM25 ハイブリッド検索
- 📚 ChromaDB ベクトルデータベース
- 🔄 ストリーミング・ブロッキング両対応API
- 📈 GPU使用率監視

## 🔧 設定

### 環境変数

| 変数名 | デフォルト値 | 説明 |
|--------|-------------|------|
| `LLM_MODEL` | `hf.co/mmnga/Llama-3.1-Swallow-8B-Instruct-v0.5-gguf:Q4_K_M` | 使用するLLMモデル |
| `OLLAMA_HOST` | `http://ollama:11434` | OllamaサーバーのURL |
| `BACKEND_URL` | `http://backend:8000` | バックエンドAPI URL |
| `CHROMA_TELEMETRY` | `False` | ChromaDBテレメトリ無効化 |

### ポート設定

| サービス | ポート | 説明 |
|----------|--------|------|
| Nginx | 80, 443 | HTTPSリバースプロキシ |
| Streamlit | 8501 | フロントエンドWebUI |
| FastAPI | 8000 | バックエンドAPI |
| Ollama | 11434 | LLMサーバー |

## 📝 管理コマンド

### ログ確認
```bash
# 全サービスのログ
docker-compose -f docker-compose.prod.yml logs -f

# 特定サービスのログ
docker-compose -f docker-compose.prod.yml logs -f backend
docker-compose -f docker-compose.prod.yml logs -f frontend
```

### 停止・再起動
```bash
# 停止
docker-compose -f docker-compose.prod.yml down

# 再起動
docker-compose -f docker-compose.prod.yml restart

# 強制再ビルド
docker-compose -f docker-compose.prod.yml build --no-cache
```

### データ管理
```bash
# データバックアップ
docker run --rm -v kitakyushu-waste-chatbot-enhanced_ollama_data:/data -v $(pwd):/backup ubuntu tar czf /backup/ollama_backup.tar.gz -C /data .

# データリストア
docker run --rm -v kitakyushu-waste-chatbot-enhanced_ollama_data:/data -v $(pwd):/backup ubuntu tar xzf /backup/ollama_backup.tar.gz -C /data
```

## 🔒 セキュリティ

### 本番環境での注意事項

1. **SSL証明書**: 自己署名証明書の代わりにLet's Encryptなどを使用
2. **環境変数**: `.env`ファイルで機密情報を管理
3. **ファイアウォール**: 必要なポートのみ開放
4. **アップデート**: 定期的なセキュリティアップデート

### 推奨セキュリティ設定

```bash
# Let's Encrypt証明書取得例
certbot --nginx -d yourdomain.com

# ファイアウォール設定例（Ubuntu）
ufw allow 80
ufw allow 443
ufw enable
```

## 🐛 トラブルシューティング

### よくある問題

1. **GPU認識しない**
   ```bash
   # NVIDIA Container Toolkit確認
   docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
   ```

2. **メモリ不足**
   ```bash
   # Docker設定でメモリ上限を増加
   # または軽量モデルに変更
   ```

3. **ポート競合**
   ```bash
   # 使用中ポート確認
   sudo netstat -tulpn | grep :8000
   ```

## 📞 サポート

問題が発生した場合は以下を確認してください：

1. [Issues](https://github.com/Hisayuki04072/kitakyushu-waste-chatbot-enhanced/issues)
2. `docker-compose logs`でエラーログを確認
3. システム要件を満たしているか確認

## 📄 ライセンス

このプロジェクトはMITライセンスの下で公開されています。
