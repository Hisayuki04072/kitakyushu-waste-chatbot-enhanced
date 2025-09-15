#!/bin/bash

# AWS EC2 デプロイ実行スクリプト
# SSH接続後にこのスクリプトを実行してください

echo "🚀 北九州市ごみ分別チャットボット - EC2デプロイ実行"
echo "=============================================="

# 色付きログ
log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }
log_step() { echo -e "\033[36m[STEP]\033[0m $1"; }

# 実行前確認
log_step "環境確認"
log_info "OS: $(lsb_release -d | cut -f2)"
log_info "CPU: $(nproc) cores"
log_info "RAM: $(free -h | awk '/^Mem:/ {print $2}')"
log_info "Disk: $(df -h / | awk 'NR==2 {print $4}') available"

# GPU確認
if command -v nvidia-smi &> /dev/null; then
    log_info "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
    GPU_AVAILABLE=true
else
    log_warn "GPU: Not detected (CPU mode)"
    GPU_AVAILABLE=false
fi

echo ""
read -p "このEC2インスタンスでデプロイを開始しますか？ (y/N): " confirm
if [[ ! $confirm =~ ^[Yy]$ ]]; then
    log_info "デプロイをキャンセルしました"
    exit 0
fi

echo ""

# Step 1: 環境セットアップ
log_step "Step 1: 環境セットアップ"
if [ ! -d "kitakyushu-waste-chatbot-enhanced" ]; then
    log_info "環境セットアップスクリプトを実行..."
    curl -sSL https://raw.githubusercontent.com/Hisayuki04072/kitakyushu-waste-chatbot-enhanced/main/setup-aws-env.sh | bash
    
    log_warn "Dockerグループが追加されました。以下のコマンドを実行してください:"
    log_warn "newgrp docker"
    log_warn "その後、再度このスクリプトを実行してください"
    exit 0
else
    log_info "プロジェクトディレクトリが存在します"
fi

# Step 2: ディレクトリ移動
log_step "Step 2: プロジェクトディレクトリに移動"
cd kitakyushu-waste-chatbot-enhanced
log_info "現在のディレクトリ: $(pwd)"

# Step 3: Docker確認
log_step "Step 3: Docker環境確認"
if ! docker info &> /dev/null; then
    log_error "Dockerにアクセスできません"
    log_warn "以下を実行してください:"
    log_warn "  newgrp docker"
    log_warn "  または、一度ログアウトして再ログインしてください"
    exit 1
fi
log_info "Docker: $(docker --version)"
log_info "Docker Compose: $(docker-compose --version)"

# Step 4: 設定ファイル確認
log_step "Step 4: 設定ファイル確認"
if [ ! -f ".env" ]; then
    log_info ".envファイルをコピー中..."
    cp .env.aws .env
fi

if [ ! -f "docker-compose.aws.yml" ]; then
    log_error "docker-compose.aws.yml が見つかりません"
    exit 1
fi

log_info "設定ファイル: ✓"

# Step 5: GPUモード選択
log_step "Step 5: 実行モード選択"
if [ "$GPU_AVAILABLE" = true ]; then
    echo "GPU環境が検出されました。実行モードを選択してください:"
    echo "1) GPU Mode (推奨 - 高速)"
    echo "2) CPU Mode (GPU使わない)"
    read -p "選択 (1-2): " mode_choice
    
    if [ "$mode_choice" = "2" ]; then
        log_info "CPU モードを選択"
        sed 's/nvidia//g' docker-compose.aws.yml > docker-compose.cpu.yml
        COMPOSE_FILE="docker-compose.cpu.yml"
    else
        log_info "GPU モードを選択"
        COMPOSE_FILE="docker-compose.aws.yml"
    fi
else
    log_info "CPU モードで実行"
    sed 's/nvidia//g' docker-compose.aws.yml > docker-compose.cpu.yml
    COMPOSE_FILE="docker-compose.cpu.yml"
fi

# Step 6: データディレクトリ準備
log_step "Step 6: データディレクトリ準備"
mkdir -p data logs frontend/logs ssl
chmod 755 logs frontend/logs

# Step 7: SSL証明書生成
log_step "Step 7: SSL証明書生成"
if [ ! -f "ssl/nginx.crt" ]; then
    log_info "SSL証明書を生成中..."
    PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "localhost")
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout ssl/nginx.key \
        -out ssl/nginx.crt \
        -subj "/C=JP/ST=Fukuoka/L=Kitakyushu/O=KitakyushuCity/CN=$PUBLIC_IP" &>/dev/null
    log_info "SSL証明書生成完了"
else
    log_info "SSL証明書が既に存在します"
fi

# Step 8: Docker イメージビルド
log_step "Step 8: Docker イメージビルド"
log_warn "イメージビルドを開始します（15-20分かかる場合があります）..."
read -p "続行しますか？ (y/N): " build_confirm
if [[ ! $build_confirm =~ ^[Yy]$ ]]; then
    log_info "ビルドをキャンセルしました"
    exit 0
fi

log_info "既存コンテナを停止中..."
docker-compose -f $COMPOSE_FILE down --remove-orphans &>/dev/null || true

log_info "Docker イメージをビルド中..."
docker-compose -f $COMPOSE_FILE build --no-cache

# Step 9: サービス起動
log_step "Step 9: サービス起動"
log_info "サービスを起動中..."
docker-compose -f $COMPOSE_FILE up -d

# Step 10: 起動確認
log_step "Step 10: 起動確認"
log_info "サービス起動状況:"
docker-compose -f $COMPOSE_FILE ps

# Step 11: ヘルスチェック
log_step "Step 11: ヘルスチェック"
log_info "サービスの準備ができるまで待機中..."

# Ollama準備待ち
log_info "Ollama サービス準備中（モデルダウンロード含む）..."
for i in {1..60}; do
    if curl -s http://localhost:11434/api/tags &>/dev/null; then
        log_info "✓ Ollama: 準備完了"
        break
    fi
    echo -n "."
    sleep 10
done
echo ""

# Backend準備待ち
log_info "Backend API 準備中..."
for i in {1..30}; do
    if curl -s http://localhost:8000/api/search-info &>/dev/null; then
        log_info "✓ Backend API: 準備完了"
        break
    fi
    echo -n "."
    sleep 5
done
echo ""

# Frontend準備待ち
log_info "Frontend 準備中..."
for i in {1..20}; do
    if curl -s http://localhost:8501/_stcore/health &>/dev/null; then
        log_info "✓ Frontend: 準備完了"
        break
    fi
    echo -n "."
    sleep 3
done
echo ""

# Step 12: 最終確認
log_step "Step 12: 最終確認"
log_info "全サービスの最終チェック..."

# 各エンドポイントテスト
BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/search-info)
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8501/_stcore/health)
NGINX_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health)

PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || hostname -I | awk '{print $1}')

echo ""
echo "=============================================="
log_info "🎉 デプロイ完了!"
echo "=============================================="
echo ""
echo "📊 サービス状況:"
echo "  Backend API: $([ "$BACKEND_STATUS" = "200" ] && echo "✓ 正常" || echo "✗ エラー ($BACKEND_STATUS)")"
echo "  Frontend:    $([ "$FRONTEND_STATUS" = "200" ] && echo "✓ 正常" || echo "✗ エラー ($FRONTEND_STATUS)")"
echo "  Nginx:       $([ "$NGINX_STATUS" = "200" ] && echo "✓ 正常" || echo "✗ エラー ($NGINX_STATUS)")"
echo ""
echo "🌐 アクセス情報:"
echo "  Web UI:   http://$PUBLIC_IP"
echo "  HTTPS:    https://$PUBLIC_IP (自己署名証明書)"
echo "  API:      http://$PUBLIC_IP:8000/api/search-info"
echo ""
echo "📋 管理コマンド:"
echo "  ログ確認:     docker-compose -f $COMPOSE_FILE logs -f"
echo "  再起動:       docker-compose -f $COMPOSE_FILE restart"
echo "  停止:         docker-compose -f $COMPOSE_FILE down"
echo "  状況確認:     docker-compose -f $COMPOSE_FILE ps"
echo ""
echo "⚠️  重要事項:"
echo "  • 初回はOllamaモデルダウンロードで時間がかかります"
echo "  • HTTPSは自己署名証明書です"
echo "  • データは data/ フォルダに保存されます"
echo ""
echo "=============================================="

# エラーがある場合のログ表示
if [ "$BACKEND_STATUS" != "200" ] || [ "$FRONTEND_STATUS" != "200" ] || [ "$NGINX_STATUS" != "200" ]; then
    echo ""
    log_warn "一部サービスでエラーが発生しています"
    log_warn "以下のコマンドでログを確認してください:"
    echo "  docker-compose -f $COMPOSE_FILE logs backend"
    echo "  docker-compose -f $COMPOSE_FILE logs frontend"
    echo "  docker-compose -f $COMPOSE_FILE logs nginx"
fi

echo ""
log_info "デプロイスクリプト完了"
