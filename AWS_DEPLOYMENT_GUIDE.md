# AWS環境でのデプロイガイド
# 北九州市ごみ分別チャットボット

## 🚀 AWS EC2での自動デプロイ

### 前提条件
- AWS EC2インスタンス（推奨: g4dn.xlarge以上 GPU付き、またはt3.large以上 CPU版）
- Ubuntu 20.04 LTS以上
- 8GB以上のRAM
- 20GB以上のストレージ
- セキュリティグループでポート80, 443を開放

### 1. 環境準備
```bash
# システムアップデート
sudo apt update && sudo apt upgrade -y

# Dockerインストール
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Docker Composeインストール
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# GPU環境の場合（オプション）
# NVIDIA Docker Runtimeインストール
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt update && sudo apt install -y nvidia-docker2
sudo systemctl restart docker
```

### 2. アプリケーションデプロイ
```bash
# リポジトリクローン
git clone https://github.com/Hisayuki04072/kitakyushu-waste-chatbot-enhanced.git
cd kitakyushu-waste-chatbot-enhanced

# 実行権限付与
chmod +x deploy-aws.sh

# デプロイ実行
./deploy-aws.sh
```

### 3. 手動デプロイ（カスタマイズが必要な場合）
```bash
# 環境設定
cp .env.aws .env
# 必要に応じて.envを編集

# SSL証明書生成
mkdir -p ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout ssl/nginx.key \
    -out ssl/nginx.crt \
    -subj "/C=JP/ST=Fukuoka/L=Kitakyushu/O=KitakyushuCity/CN=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"

# データディレクトリ準備
mkdir -p data logs frontend/logs
chmod 755 logs frontend/logs

# GPU版デプロイ
docker-compose -f docker-compose.aws.yml up -d

# CPU版デプロイ（GPU無し環境）
sed 's/nvidia//g' docker-compose.aws.yml > docker-compose.cpu.yml
docker-compose -f docker-compose.cpu.yml up -d
```

## 📊 モニタリング・管理

### サービス状況確認
```bash
# コンテナ状況
docker-compose -f docker-compose.aws.yml ps

# ログ確認
docker-compose -f docker-compose.aws.yml logs -f

# 個別サービスログ
docker-compose -f docker-compose.aws.yml logs -f ollama
docker-compose -f docker-compose.aws.yml logs -f backend
docker-compose -f docker-compose.aws.yml logs -f frontend
```

### ヘルスチェック
```bash
# バックエンドAPI
curl http://localhost:8000/api/search-info

# フロントエンド
curl http://localhost:8501/_stcore/health

# Nginx
curl http://localhost/health
```

### サービス管理
```bash
# 再起動
docker-compose -f docker-compose.aws.yml restart

# 停止
docker-compose -f docker-compose.aws.yml down

# 完全リセット（データ保持）
docker-compose -f docker-compose.aws.yml down
docker-compose -f docker-compose.aws.yml up -d

# 完全リセット（データ削除）
docker-compose -f docker-compose.aws.yml down -v
docker-compose -f docker-compose.aws.yml up -d
```

## 🔧 トラブルシューティング

### よくある問題

#### 1. Ollamaモデルのダウンロードが遅い
```bash
# 進行状況確認
docker-compose -f docker-compose.aws.yml logs -f ollama

# 手動でモデルダウンロード
docker-compose -f docker-compose.aws.yml exec ollama ollama pull hf.co/mmnga/Llama-3.1-Swallow-8B-Instruct-v0.5-gguf:Q4_K_M
```

#### 2. メモリ不足エラー
```bash
# メモリ使用量確認
docker stats

# より軽量なモデルに変更（.envファイル編集）
LLM_MODEL=hf.co/mmnga/Llama-3.1-Swallow-8B-Instruct-v0.5-gguf:Q4_0
```

#### 3. GPU認識しない
```bash
# GPU確認
nvidia-smi
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi

# CPU版に切り替え
sed 's/nvidia//g' docker-compose.aws.yml > docker-compose.cpu.yml
docker-compose -f docker-compose.cpu.yml up -d
```

#### 4. セキュリティグループ設定
- ポート80 (HTTP): 0.0.0.0/0
- ポート443 (HTTPS): 0.0.0.0/0
- 必要に応じてポート8000, 8501も開放

## 🌐 アクセス方法

デプロイ完了後、以下でアクセス可能：

- **Web UI**: `http://YOUR_EC2_PUBLIC_IP`
- **HTTPS**: `https://YOUR_EC2_PUBLIC_IP` (セルフサイン証明書)
- **API**: `http://YOUR_EC2_PUBLIC_IP/api/search-info`

## 📈 性能最適化

### EC2インスタンス推奨構成

| 用途 | インスタンスタイプ | vCPU | RAM | GPU | 月額概算 |
|------|-------------------|------|-----|-----|----------|
| 開発・テスト | t3.large | 2 | 8GB | - | $60 |
| 小規模本番 | t3.xlarge | 4 | 16GB | - | $120 |
| GPU推論 | g4dn.xlarge | 4 | 16GB | T4 | $380 |
| 大規模本番 | g4dn.2xlarge | 8 | 32GB | T4 | $600 |

### チューニング

#### メモリ最適化
```bash
# Docker メモリ制限
# docker-compose.aws.ymlでメモリ制限設定済み
```

#### GPU最適化
```bash
# CUDA メモリ管理
docker-compose -f docker-compose.aws.yml exec ollama sh -c "
export CUDA_VISIBLE_DEVICES=0
export OLLAMA_GPU_LAYERS=32
ollama serve
"
```

## 🔒 セキュリティ

### SSL証明書（本番環境）
```bash
# Let's Encrypt証明書（ドメインが必要）
sudo snap install certbot --classic
sudo certbot certonly --standalone -d your-domain.com

# 証明書をNginxに設定
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ssl/nginx.crt
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ssl/nginx.key
```

### ファイアウォール設定
```bash
# UFWファイアウォール
sudo ufw enable
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
```

## 📝 ログ管理

### ログローテーション
```bash
# logrotate設定
sudo tee /etc/logrotate.d/chatbot << EOF
/home/ubuntu/kitakyushu-waste-chatbot-enhanced/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    notifempty
    create 644 ubuntu ubuntu
}
EOF
```

## 🔄 アップデート

### アプリケーション更新
```bash
# 最新版取得
git pull origin main

# コンテナ再ビルド
docker-compose -f docker-compose.aws.yml down
docker-compose -f docker-compose.aws.yml build --no-cache
docker-compose -f docker-compose.aws.yml up -d
```

### バックアップ
```bash
# データバックアップ
tar -czf backup-$(date +%Y%m%d).tar.gz data/ logs/ chroma_db/

# S3にバックアップ（AWS CLI設定済みの場合）
aws s3 cp backup-$(date +%Y%m%d).tar.gz s3://your-backup-bucket/
```
