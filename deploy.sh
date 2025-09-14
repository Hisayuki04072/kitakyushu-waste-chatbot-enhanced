#!/bin/bash

# 北九州市ごみ分別チャットボット デプロイスクリプト

echo "=== 北九州市ごみ分別チャットボット デプロイ開始 ==="

# 前回のコンテナを停止・削除
echo "既存のコンテナを停止中..."
docker-compose -f docker-compose.prod.yml down

# イメージをビルド
echo "Dockerイメージをビルド中..."
docker-compose -f docker-compose.prod.yml build --no-cache

# SSL証明書を生成（存在しない場合）
if [ ! -f ssl/cert.pem ]; then
    echo "SSL証明書を生成中..."
    ./generate_ssl.sh
fi

# データディレクトリを作成
mkdir -p data
mkdir -p logs
mkdir -p frontend/logs

# コンテナを起動
echo "コンテナを起動中..."
docker-compose -f docker-compose.prod.yml up -d

# 起動確認
echo "サービス起動確認中..."
sleep 30

# ヘルスチェック
echo "ヘルスチェック実行中..."
if curl -f http://localhost:8000/api/search-info > /dev/null 2>&1; then
    echo "✅ バックエンドが正常に起動しました"
else
    echo "❌ バックエンドの起動に失敗しました"
fi

if curl -f http://localhost:8501/_stcore/health > /dev/null 2>&1; then
    echo "✅ フロントエンドが正常に起動しました"
else
    echo "❌ フロントエンドの起動に失敗しました"
fi

echo ""
echo "=== デプロイ完了 ==="
echo "アクセス方法:"
echo "  HTTP:  http://localhost (→ HTTPSにリダイレクト)"
echo "  HTTPS: https://localhost"
echo "  フロントエンド直接: http://localhost:8501"
echo "  バックエンドAPI: http://localhost:8000"
echo ""
echo "ログ確認: docker-compose -f docker-compose.prod.yml logs -f"
echo "停止方法: docker-compose -f docker-compose.prod.yml down"
