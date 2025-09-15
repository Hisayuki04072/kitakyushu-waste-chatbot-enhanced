#!/bin/bash

# EC2 ChatBot 完全デプロイスクリプト
# IPアドレス自動取得・設定込み

echo "🚀 EC2 ChatBot デプロイ開始"
echo "========================================"

# 色付きログ関数
log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }
log_step() { echo -e "\033[36m[STEP]\033[0m $1"; }

# IPアドレス自動取得
get_public_ip() {
    local ip
    # AWS メタデータサービスから取得
    ip=$(curl -s --max-time 5 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null)
    if [ -z "$ip" ]; then
        # 外部サービスから取得
        ip=$(curl -s --max-time 5 http://ipecho.net/plain 2>/dev/null)
    fi
    if [ -z "$ip" ]; then
        # ローカルIPから推測
        ip=$(hostname -I | awk '{print $1}')
    fi
    echo "$ip"
}

# ステップ1: 環境確認
log_step "Step 1: 環境確認"
log_info "OS: $(lsb_release -d | cut -f2)"
log_info "CPU: $(nproc) cores"
log_info "RAM: $(free -h | awk '/^Mem:/ {print $2}')"

# パブリックIP取得
PUBLIC_IP=$(get_public_ip)
PRIVATE_IP=$(hostname -I | awk '{print $1}')

log_info "Private IP: $PRIVATE_IP"
log_info "Public IP: $PUBLIC_IP"

# GPU確認
if command -v nvidia-smi &> /dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
    log_info "GPU: $GPU_INFO"
    USE_GPU=true
else
    log_warn "GPU: Not detected (CPU mode)"
    USE_GPU=false
fi

# ステップ2: 必要ツール確認
log_step "Step 2: 必要ツール確認"
if ! command -v docker &> /dev/null; then
    log_error "Dockerがインストールされていません"
    log_warn "setup-aws-env.sh を先に実行してください"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    log_error "Docker Composeがインストールされていません"
    exit 1
fi

log_info "Docker: $(docker --version | cut -d' ' -f3 | tr -d ',')"
log_info "Docker Compose: $(docker-compose --version | cut -d' ' -f3 | tr -d ',')"

# ステップ3: プロジェクト確認
log_step "Step 3: プロジェクト確認"
if [ ! -f "docker-compose.aws.yml" ]; then
    log_error "docker-compose.aws.yml が見つかりません"
    log_warn "プロジェクトディレクトリで実行してください"
    exit 1
fi

# ステップ4: 環境設定
log_step "Step 4: 環境設定"

# .envファイル作成/更新
cat > .env << EOF
# ChromaDB Telemetry無効化設定
ANONYMIZED_TELEMETRY=False
CHROMA_TELEMETRY=False
CHROMA_ANALYTICS_DISABLED=True
CHROMA_DISABLE_TELEMETRY=True
CHROMA_DISABLE_ANALYTICS=True
CHROMA_SERVER_NOFILE=1
POSTHOG_DISABLED=True
DO_NOT_TRACK=1

# AWS EC2環境設定
EMBED_MODEL=bge-m3
LLM_MODEL=hf.co/mmnga/Llama-3.1-Swallow-8B-Instruct-v0.5-gguf:Q4_K_M
OLLAMA_HOST=http://ollama:11434
BACKEND_URL=http://backend:8000

# ネットワーク設定
PUBLIC_IP=$PUBLIC_IP
PRIVATE_IP=$PRIVATE_IP

# セキュリティ設定
SECURE_MODE=true
PYTHONPATH=/app
AWS_DEPLOYMENT=true

# ストリームリット設定
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
EOF

log_info "環境変数設定完了"

# ステップ5: GPU/CPU判定
log_step "Step 5: 実行モード選択"
if [ "$USE_GPU" = true ]; then
    log_info "GPU モードで実行します"
    COMPOSE_FILE="docker-compose.aws.yml"
else
    log_info "CPU モードで実行します"
    # GPU設定を削除したCPU版作成
    sed '/nvidia/d; /gpu/d; /GPU/d' docker-compose.aws.yml > docker-compose.cpu.yml
    COMPOSE_FILE="docker-compose.cpu.yml"
fi

# ステップ6: SSL証明書生成
log_step "Step 6: SSL証明書生成"
mkdir -p ssl

if [ ! -f "ssl/nginx.crt" ] || [ ! -f "ssl/nginx.key" ]; then
    log_info "SSL証明書を生成中..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout ssl/nginx.key \
        -out ssl/nginx.crt \
        -subj "/C=JP/ST=Fukuoka/L=Kitakyushu/O=KitakyushuCity/CN=$PUBLIC_IP" &>/dev/null
    log_info "SSL証明書生成完了"
else
    log_info "SSL証明書が既に存在します"
fi

# ステップ7: データディレクトリ準備
log_step "Step 7: データディレクトリ準備"
mkdir -p data logs frontend/logs chroma_db
chmod 755 logs frontend/logs
log_info "データディレクトリ準備完了"

# ステップ8: 既存サービス停止
log_step "Step 8: 既存サービス停止"
docker-compose -f $COMPOSE_FILE down --remove-orphans &>/dev/null || true
log_info "既存サービス停止完了"

# ステップ9: イメージビルド
log_step "Step 9: Docker イメージビルド"
log_warn "イメージビルドを開始します（10-20分かかります）"
echo -n "ビルド進行中"

# バックグラウンドでビルド、進捗表示
docker-compose -f $COMPOSE_FILE build --no-cache &
BUILD_PID=$!

# 進捗表示
while kill -0 $BUILD_PID 2>/dev/null; do
    echo -n "."
    sleep 5
done
wait $BUILD_PID
BUILD_EXIT_CODE=$?

echo ""
if [ $BUILD_EXIT_CODE -eq 0 ]; then
    log_info "Docker イメージビルド完了"
else
    log_error "Docker イメージビルドに失敗しました"
    exit 1
fi

# ステップ10: サービス起動
log_step "Step 10: サービス起動"
log_info "ChatBot サービスを起動中..."
docker-compose -f $COMPOSE_FILE up -d

# サービス確認
sleep 5
log_info "起動中のサービス:"
docker-compose -f $COMPOSE_FILE ps

# ステップ11: ヘルスチェック
log_step "Step 11: ヘルスチェック"
log_info "サービス準備完了まで待機中..."

# Ollama待ち（最重要）
log_info "Ollama準備中（モデルダウンロード含む）..."
for i in {1..90}; do
    if curl -s http://localhost:11434/api/tags &>/dev/null; then
        log_info "✓ Ollama: 準備完了"
        break
    fi
    [ $((i % 6)) -eq 0 ] && echo -n " ${i}0s"
    echo -n "."
    sleep 10
done
echo ""

# Backend API待ち
log_info "Backend API準備中..."
for i in {1..30}; do
    if curl -s http://localhost:8000/api/search-info &>/dev/null; then
        log_info "✓ Backend API: 準備完了"
        break
    fi
    echo -n "."
    sleep 5
done
echo ""

# Frontend待ち
log_info "Frontend準備中..."
for i in {1..20}; do
    if curl -s http://localhost:8501/_stcore/health &>/dev/null; then
        log_info "✓ Frontend: 準備完了"
        break
    fi
    echo -n "."
    sleep 3
done
echo ""

# ステップ12: 最終確認
log_step "Step 12: 最終確認"

# エンドポイントテスト
BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/search-info 2>/dev/null || echo "000")
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8501/_stcore/health 2>/dev/null || echo "000")
NGINX_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health 2>/dev/null || echo "000")

# 結果表示
echo ""
echo "=========================================="
log_info "🎉 EC2 ChatBot デプロイ完了!"
echo "=========================================="
echo ""
echo "🌐 アクセス情報:"
echo "  メインURL:    http://$PUBLIC_IP"
echo "  HTTPS:        https://$PUBLIC_IP"
echo "  API:          http://$PUBLIC_IP:8000/api/search-info"
echo "  Streamlit:    http://$PUBLIC_IP:8501"
echo ""
echo "📊 サービス状況:"
echo "  Backend API:  $([ "$BACKEND_STATUS" = "200" ] && echo "✓ 正常" || echo "✗ エラー ($BACKEND_STATUS)")"
echo "  Frontend:     $([ "$FRONTEND_STATUS" = "200" ] && echo "✓ 正常" || echo "✗ エラー ($FRONTEND_STATUS)")"
echo "  Nginx:        $([ "$NGINX_STATUS" = "200" ] && echo "✓ 正常" || echo "✗ エラー ($NGINX_STATUS)")"
echo ""
echo "🔧 管理コマンド:"
echo "  ログ確認:     docker-compose -f $COMPOSE_FILE logs -f"
echo "  再起動:       docker-compose -f $COMPOSE_FILE restart"
echo "  停止:         docker-compose -f $COMPOSE_FILE down"
echo "  状況確認:     docker-compose -f $COMPOSE_FILE ps"
echo ""
echo "📱 モバイルアクセス:"
echo "  QRコード生成: qrencode -t ansiutf8 http://$PUBLIC_IP"
echo ""
echo "⚠️  重要事項:"
echo "  • 初回起動時はOllamaモデルダウンロードで追加時間要"
echo "  • HTTPSは自己署名証明書（ブラウザ警告を許可）"
echo "  • セキュリティグループでポート80,443を開放確認"
echo "  • Elastic IPを設定すると固定IPで運用可能"
echo ""
echo "=========================================="

# ログ出力
if [ "$BACKEND_STATUS" != "200" ] || [ "$FRONTEND_STATUS" != "200" ]; then
    echo ""
    log_warn "サービスエラーが検出されました"
    log_warn "詳細ログ確認:"
    echo "  Backend:  docker-compose -f $COMPOSE_FILE logs backend | tail -20"
    echo "  Frontend: docker-compose -f $COMPOSE_FILE logs frontend | tail -20"
    echo "  Ollama:   docker-compose -f $COMPOSE_FILE logs ollama | tail -20"
fi

log_info "デプロイスクリプト完了 - ChatBotをお楽しみください！"
