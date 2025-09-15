#!/bin/bash

# AWS環境用デプロイスクリプト
# 北九州市ごみ分別チャットボット

set -e

# 色付きログ関数
log_info() {
    echo -e "\033[32m[INFO]\033[0m $1"
}

log_warn() {
    echo -e "\033[33m[WARN]\033[0m $1"
}

log_error() {
    echo -e "\033[31m[ERROR]\033[0m $1"
}

# AWS環境チェック
check_aws_environment() {
    log_info "AWS環境をチェック中..."
    
    # Docker確認
    if ! command -v docker &> /dev/null; then
        log_error "Dockerがインストールされていません"
        exit 1
    fi
    
    # Docker Compose確認
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Composeがインストールされていません"
        exit 1
    fi
    
    # GPU確認（オプション）
    if command -v nvidia-smi &> /dev/null; then
        log_info "NVIDIA GPU検出: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
    else
        log_warn "GPU未検出: CPUモードで動作します"
    fi
    
    log_info "環境チェック完了"
}

# 環境変数設定
setup_environment() {
    log_info "環境変数を設定中..."
    
    # .envファイルが存在しない場合は作成
    if [ ! -f .env ]; then
        log_info ".envファイルを作成中..."
        cat > .env << 'EOF'
# ChromaDB Telemetry無効化設定
ANONYMIZED_TELEMETRY=False
CHROMA_TELEMETRY=False
CHROMA_ANALYTICS_DISABLED=True
CHROMA_DISABLE_TELEMETRY=True
CHROMA_DISABLE_ANALYTICS=True
CHROMA_SERVER_NOFILE=1
POSTHOG_DISABLED=True
DO_NOT_TRACK=1

# AWS環境設定
EMBED_MODEL=bge-m3
LLM_MODEL=hf.co/mmnga/Llama-3.1-Swallow-8B-Instruct-v0.5-gguf:Q4_K_M
OLLAMA_HOST=http://ollama:11434
BACKEND_URL=http://backend:8000

# セキュリティ設定
SECURE_MODE=true
PYTHONPATH=/app
EOF
    else
        log_info ".envファイルが既に存在します"
    fi
    
    # 環境変数をエクスポート
    export $(cat .env | grep -v '^#' | xargs)
    log_info "環境変数設定完了"
}

# SSL証明書生成（セルフサイン）
generate_ssl_certificates() {
    log_info "SSL証明書を生成中..."
    
    mkdir -p ssl
    
    if [ ! -f ssl/nginx.crt ] || [ ! -f ssl/nginx.key ]; then
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout ssl/nginx.key \
            -out ssl/nginx.crt \
            -subj "/C=JP/ST=Fukuoka/L=Kitakyushu/O=KitakyushuCity/CN=chatbot.kitakyushu.local"
        
        log_info "SSL証明書生成完了"
    else
        log_info "SSL証明書が既に存在します"
    fi
}

# Docker イメージビルド
build_images() {
    log_info "Dockerイメージをビルド中..."
    
    # 古いコンテナを停止・削除
    log_info "既存のコンテナを停止中..."
    docker-compose -f docker-compose.prod.yml down --remove-orphans || true
    
    # イメージビルド
    log_info "イメージをビルド中（これには時間がかかる場合があります）..."
    docker-compose -f docker-compose.prod.yml build --no-cache
    
    log_info "Dockerイメージビルド完了"
}

# データディレクトリ準備
prepare_data() {
    log_info "データディレクトリを準備中..."
    
    # 必要なディレクトリ作成
    mkdir -p data logs frontend/logs
    
    # サンプルデータ確認
    if [ -d data ] && [ "$(ls -A data)" ]; then
        log_info "データファイルが存在します: $(ls data/ | wc -l)個のファイル"
    else
        log_warn "データディレクトリが空です。CSVファイルをアップロードしてください"
    fi
    
    # ログディレクトリの権限設定
    chmod 755 logs frontend/logs
    
    log_info "データディレクトリ準備完了"
}

# サービス起動
start_services() {
    log_info "サービスを起動中..."
    
    # バックグラウンドでサービス起動
    docker-compose -f docker-compose.prod.yml up -d
    
    log_info "サービス起動完了"
    log_info "起動状況を確認中..."
    
    # 起動確認
    sleep 10
    docker-compose -f docker-compose.prod.yml ps
}

# ヘルスチェック
health_check() {
    log_info "ヘルスチェックを実行中..."
    
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        log_info "ヘルスチェック試行 $attempt/$max_attempts"
        
        # バックエンドチェック
        if curl -s -f http://localhost:8000/api/search-info > /dev/null 2>&1; then
            log_info "✅ バックエンド: 正常"
            break
        else
            log_warn "⏳ バックエンド: 起動中..."
        fi
        
        sleep 10
        ((attempt++))
    done
    
    if [ $attempt -gt $max_attempts ]; then
        log_error "ヘルスチェックタイムアウト"
        return 1
    fi
    
    log_info "✅ 全サービス正常起動完了"
}

# AWS固有の設定
configure_aws_specific() {
    log_info "AWS固有の設定を適用中..."
    
    # セキュリティグループの確認指示
    log_info "以下のポートがAWSセキュリティグループで開放されていることを確認してください:"
    log_info "  - 80 (HTTP)"
    log_info "  - 443 (HTTPS)"
    log_info "  - 8000 (バックエンドAPI - 必要に応じて)"
    log_info "  - 8501 (フロントエンド - 必要に応じて)"
    
    # EBS最適化の確認
    if [ -d /dev/xvdf ]; then
        log_info "EBSボリュームが検出されました"
    fi
    
    log_info "AWS固有設定完了"
}

# メイン実行
main() {
    log_info "🚀 AWS環境デプロイを開始します..."
    log_info "プロジェクト: 北九州市ごみ分別チャットボット"
    
    check_aws_environment
    setup_environment
    generate_ssl_certificates
    prepare_data
    build_images
    configure_aws_specific
    start_services
    health_check
    
    log_info "🎉 デプロイ完了!"
    log_info ""
    log_info "📋 アクセス情報:"
    log_info "  Web UI: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || hostname -I | awk '{print $1}')"
    log_info "  HTTPS: https://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || hostname -I | awk '{print $1}')"
    log_info "  API: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || hostname -I | awk '{print $1}'):8000"
    log_info ""
    log_info "📊 管理コマンド:"
    log_info "  ログ確認: docker-compose -f docker-compose.prod.yml logs -f"
    log_info "  サービス停止: docker-compose -f docker-compose.prod.yml down"
    log_info "  再起動: docker-compose -f docker-compose.prod.yml restart"
    log_info ""
    log_info "⚠️  初回起動時はOllamaモデルのダウンロードに時間がかかります"
    log_info "   モデルダウンロード進行状況: docker-compose -f docker-compose.prod.yml logs -f ollama"
}

# スクリプト実行
main "$@"
