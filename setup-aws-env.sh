#!/bin/bash

# AWS EC2 クイックスタートスクリプト
# SSH接続後、このスクリプトを実行してください

set -e

echo "🚀 北九州市ごみ分別チャットボット - AWS環境セットアップ"
echo "================================================"

# 色付きログ関数
log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }

# 1. システム更新
log_info "システムを更新中..."
sudo apt update && sudo apt upgrade -y

# 2. 必要なツールインストール
log_info "必要なツールをインストール中..."
sudo apt install -y curl wget git htop unzip

# 3. Dockerインストール
if ! command -v docker &> /dev/null; then
    log_info "Dockerをインストール中..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
else
    log_info "Docker は既にインストールされています"
fi

# 4. Docker Composeインストール
if ! command -v docker-compose &> /dev/null; then
    log_info "Docker Composeをインストール中..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
else
    log_info "Docker Compose は既にインストールされています"
fi

# 5. GPU環境確認・設定（オプション）
if command -v nvidia-smi &> /dev/null; then
    log_info "NVIDIA GPU検出: NVIDIA Docker Runtimeをインストール中..."
    distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
    if [ ! -f /etc/apt/sources.list.d/nvidia-docker.list ]; then
        curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
        curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
        sudo apt update && sudo apt install -y nvidia-docker2
        sudo systemctl restart docker
    fi
else
    log_warn "GPU未検出: CPUモードで動作します"
fi

# 6. ファイアウォール設定
log_info "ファイアウォールを設定中..."
sudo ufw --force enable
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS

# 7. リポジトリクローン（まだの場合）
if [ ! -d "kitakyushu-waste-chatbot-enhanced" ]; then
    log_info "リポジトリをクローン中..."
    git clone https://github.com/Hisayuki04072/kitakyushu-waste-chatbot-enhanced.git
fi

# 8. ディレクトリ移動
cd kitakyushu-waste-chatbot-enhanced

# 9. デプロイスクリプト実行権限付与
chmod +x deploy-aws.sh

log_info "✅ 環境セットアップ完了!"
log_info ""
log_info "📋 次のステップ:"
log_info "1. Docker グループに追加されました - 再ログインまたは以下を実行:"
log_info "   newgrp docker"
log_info ""
log_info "2. アプリケーションをデプロイ:"
log_info "   ./deploy-aws.sh"
log_info ""
log_info "3. 手動デプロイの場合:"
log_info "   docker-compose -f docker-compose.aws.yml up -d"
log_info ""
log_info "🌐 デプロイ後のアクセス:"
log_info "   Web UI: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || hostname -I | awk '{print $1}')"

echo "================================================"
