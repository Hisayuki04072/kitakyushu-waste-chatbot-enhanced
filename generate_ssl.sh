#!/bin/bash

# SSL証明書ディレクトリを作成
mkdir -p ssl

# 自己署名証明書を生成（本番環境では Let's Encrypt などを使用）
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout ssl/key.pem \
    -out ssl/cert.pem \
    -subj "/C=JP/ST=Fukuoka/L=Kitakyushu/O=City/CN=localhost"

echo "SSL証明書が生成されました: ssl/cert.pem, ssl/key.pem"
echo "本番環境では Let's Encrypt などの正式な証明書を使用してください。"
