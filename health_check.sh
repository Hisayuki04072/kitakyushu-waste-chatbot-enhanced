#!/bin/bash

# 北九州市ごみ分別チャットボット ヘルスチェックスクリプト

echo "=== 北九州市ごみ分別チャットボット ヘルスチェック ==="

# サービス状態確認
echo "📊 コンテナ状態確認:"
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "🔍 サービス詳細チェック:"

# Ollama確認
echo -n "Ollama LLMサーバー: "
if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✅ 正常"
else
    echo "❌ 異常"
fi

# バックエンド確認
echo -n "バックエンドAPI: "
if curl -sf http://localhost:8000/api/search-info > /dev/null 2>&1; then
    echo "✅ 正常"
else
    echo "❌ 異常"
fi

# フロントエンド確認
echo -n "フロントエンドUI: "
if curl -sf http://localhost:8501/_stcore/health > /dev/null 2>&1; then
    echo "✅ 正常"
else
    echo "❌ 異常"
fi

# Nginx確認
echo -n "Nginxプロキシ: "
if curl -sf -k https://localhost > /dev/null 2>&1; then
    echo "✅ 正常"
else
    echo "❌ 異常"
fi

echo ""
echo "📈 リソース使用状況:"
echo "CPU使用率:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null | grep kitakyushu

echo ""
echo "💾 ディスク使用量:"
docker system df

echo ""
echo "📝 最新ログ (最後の5行):"
echo "--- Backend ---"
docker-compose -f docker-compose.prod.yml logs --tail=5 backend 2>/dev/null || echo "ログ取得エラー"

echo "--- Frontend ---"
docker-compose -f docker-compose.prod.yml logs --tail=5 frontend 2>/dev/null || echo "ログ取得エラー"

echo ""
echo "=== ヘルスチェック完了 ==="
echo "詳細ログ: docker-compose -f docker-compose.prod.yml logs -f [service_name]"
