# EC2ネットワーク設定手順

## セキュリティグループ設定
```
セキュリティグループ名: kitakyushu-chatbot-sg

インバウンドルール:
┌─────────────┬──────┬─────────────┬─────────────────────────┐
│ タイプ      │ ポート│ ソース      │ 説明                    │
├─────────────┼──────┼─────────────┼─────────────────────────┤
│ SSH         │ 22   │ マイIP      │ 管理用SSH接続           │
│ HTTP        │ 80   │ 0.0.0.0/0   │ ChatBot Web UI          │
│ HTTPS       │ 443  │ 0.0.0.0/0   │ ChatBot Web UI (SSL)    │
│ Custom TCP  │ 8000 │ 0.0.0.0/0   │ FastAPI Backend         │
│ Custom TCP  │ 8501 │ 0.0.0.0/0   │ Streamlit Frontend      │
│ Custom TCP  │11434 │ 10.0.0.0/8  │ Ollama (内部通信)       │
└─────────────┴──────┴─────────────┴─────────────────────────┘
```

## Elastic IP設定（推奨）
1. EC2ダッシュボード → Elastic IP
2. 「新しいアドレスを割り当て」
3. 作成したEC2インスタンスに関連付け
4. 固定IPアドレスを取得

## パブリックIP確認方法
```bash
# EC2内部からパブリックIP確認
curl -s http://169.254.169.254/latest/meta-data/public-ipv4

# または
wget -qO- http://ipecho.net/plain
```
