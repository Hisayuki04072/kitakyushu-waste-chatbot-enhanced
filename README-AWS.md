# 🚀 AWS環境での簡単デプロイ手順 (AI生成、docker使用版)

## ⚡ クイックスタート（5分でデプロイ）

### 1. AWS EC2準備
- インスタンス: `t3.xlarge` 以上（推奨: `g4dn.xlarge` GPU付き）
- OS: Ubuntu 20.04 LTS
- セキュリティグループ: ポート 80, 443 を開放
- ストレージ: 25GB以上

### 2. SSH接続してスクリプト実行
```bash
# EC2にSSH接続
ssh -i your-key.pem ubuntu@YOUR_EC2_IP

# リポジトリクローンと環境セットアップ
curl -sSL https://raw.githubusercontent.com/Hisayuki04072/kitakyushu-waste-chatbot-enhanced/main/setup-aws-env.sh | bash
#もしくは
#git pull https://github.com/Hisayuki04072/kitakyushu-waste-chatbot-enhanced.git
# Dockerグループ反映（重要）
newgrp docker

# アプリケーションデプロイ
cd kitakyushu-waste-chatbot-enhanced
./deploy-aws.sh
```

### 3. アクセス確認
デプロイ完了後、ブラウザで以下にアクセス：
- **Web UI**: `http://YOUR_EC2_PUBLIC_IP`
- **HTTPS**: `https://YOUR_EC2_PUBLIC_IP`

---

## 📋 詳細手順

### 既にgit cloneが完了している場合

```bash
# プロジェクトディレクトリに移動
cd kitakyushu-waste-chatbot-enhanced

# AWS環境用の設定ファイルを確認
ls -la .env docker-compose.aws.yml deploy-aws.sh

# 自動デプロイ実行
./deploy-aws.sh
```

### 手動デプロイ

```bash
# 環境設定
cp .env.aws .env  # または既存の.envを使用

# SSL証明書生成
mkdir -p ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout ssl/nginx.key -out ssl/nginx.crt \
    -subj "/C=JP/ST=Fukuoka/L=Kitakyushu/O=KitakyushuCity/CN=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"

# データディレクトリ準備
mkdir -p data logs frontend/logs

# Docker Composeでデプロイ
docker-compose -f docker-compose.aws.yml up -d

# 進行状況確認
docker-compose -f docker-compose.aws.yml logs -f
```

---

## 🔧 管理コマンド

```bash
# サービス状況確認
docker-compose -f docker-compose.aws.yml ps

# ログ確認
docker-compose -f docker-compose.aws.yml logs -f

# 再起動
docker-compose -f docker-compose.aws.yml restart

# 停止
docker-compose -f docker-compose.aws.yml down

# ヘルスチェック
curl http://localhost/health
curl http://localhost:8000/api/search-info
```

---

## ⚠️ 重要な注意事項

1. **初回起動**: Ollamaモデルのダウンロードに15-30分かかります
2. **メモリ**: 最低8GB RAM必要、16GB推奨
3. **セキュリティ**: 本番環境では適切なSSL証明書を設定してください
4. **バックアップ**: 定期的に`data/`フォルダのバックアップを取ってください

---

## 🆘 トラブルシューティング

### サービスが起動しない
```bash
# コンテナ状況確認
docker ps -a

# エラーログ確認
docker-compose -f docker-compose.aws.yml logs ollama
docker-compose -f docker-compose.aws.yml logs backend
docker-compose -f docker-compose.aws.yml logs frontend
```

### GPU認識しない
```bash
# GPU確認
nvidia-smi

# CPU版に切り替え
sed 's/nvidia//g' docker-compose.aws.yml > docker-compose.cpu.yml
docker-compose -f docker-compose.cpu.yml up -d
```

### メモリ不足
```bash
# 軽量モデルに変更（.envファイル編集）
LLM_MODEL=hf.co/mmnga/Llama-3.1-Swallow-8B-Instruct-v0.5-gguf:Q4_0
```

---

詳細なドキュメント: [AWS_DEPLOYMENT_GUIDE.md](AWS_DEPLOYMENT_GUIDE.md)
