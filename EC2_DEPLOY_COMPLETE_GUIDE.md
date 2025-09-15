# 🚀 AWS EC2完全デプロイガイド
# 北九州市ごみ分別チャットボット

## **📋 事前準備チェックリスト**

### ✅ 必要なもの
- [ ] AWSアカウント
- [ ] SSH用キーペア(.pemファイル)
- [ ] ローカルマシンでのSSHクライアント

---

## **🏗️ ステップ1: AWS EC2インスタンス作成**

### 1.1 EC2ダッシュボードでインスタンス作成

1. **AWS マネジメントコンソール** → **EC2** → **インスタンスを起動**

2. **AMI選択**:
   ```
   Ubuntu Server 20.04 LTS (HVM), SSD Volume Type
   64ビット (x86)
   ```

3. **インスタンスタイプ選択**:
   ```
   開発・テスト環境:
   - t3.large (2 vCPU, 8 GiB RAM) - 約$60/月
   
   小規模本番環境:
   - t3.xlarge (4 vCPU, 16 GiB RAM) - 約$120/月
   
   GPU推論環境（推奨）:
   - g4dn.xlarge (4 vCPU, 16 GiB RAM, NVIDIA T4) - 約$380/月
   ```

### 1.2 ストレージ設定
```
ルートボリューム:
- サイズ: 30 GiB (推奨)
- ボリュームタイプ: gp3
- IOPS: 3000
- スループット: 125 MB/s
```

### 1.3 セキュリティグループ設定
```
新しいセキュリティグループを作成:

インバウンドルール:
┌─────────────┬──────┬─────────────┬─────────────────┐
│ タイプ      │ ポート│ ソース      │ 説明            │
├─────────────┼──────┼─────────────┼─────────────────┤
│ SSH         │ 22   │ マイIP      │ SSH接続用       │
│ HTTP        │ 80   │ 0.0.0.0/0   │ Web UI          │
│ HTTPS       │ 443  │ 0.0.0.0/0   │ Web UI (SSL)    │
│ カスタムTCP │ 8000 │ 0.0.0.0/0   │ API直接アクセス │
│ カスタムTCP │ 8501 │ 0.0.0.0/0   │ Streamlit直接   │
└─────────────┴──────┴─────────────┴─────────────────┘
```

### 1.4 キーペア設定
- **新しいキーペアを作成** → `kitakyushu-chatbot-key` として保存
- `.pem`ファイルをダウンロードし、安全な場所に保存

---

## **🔐 ステップ2: SSH接続**

### 2.1 ローカルマシンでの準備
```bash
# キーファイルの権限設定（重要）
chmod 400 kitakyushu-chatbot-key.pem

# EC2のパブリックIPを確認（EC2ダッシュボードで確認）
# 例: 52.192.XXX.XXX
```

### 2.2 SSH接続実行
```bash
# SSH接続
ssh -i kitakyushu-chatbot-key.pem ubuntu@52.192.XXX.XXX

# 接続成功例:
Welcome to Ubuntu 20.04.6 LTS (GNU/Linux 5.15.0-1041-aws x86_64)
ubuntu@ip-172-31-XX-XX:~$
```

---

## **⚙️ ステップ3: 自動環境セットアップ**

### 3.1 ワンライナーセットアップ（推奨）
```bash
# リポジトリクローンと環境自動セットアップ
curl -sSL https://raw.githubusercontent.com/Hisayuki04072/kitakyushu-waste-chatbot-enhanced/main/setup-aws-env.sh | bash
```

### 3.2 手動セットアップ（上級者向け）
```bash
# システム更新
sudo apt update && sudo apt upgrade -y

# Docker インストール
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Docker Compose インストール
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# GPU環境（g4dn.xlargeの場合）
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt update && sudo apt install -y nvidia-docker2
sudo systemctl restart docker

# リポジトリクローン
git clone https://github.com/Hisayuki04072/kitakyushu-waste-chatbot-enhanced.git
```

---

## **🚀 ステップ4: アプリケーションデプロイ**

### 4.1 Dockerグループ反映（重要）
```bash
# Dockerグループに追加後、反映させる
newgrp docker

# または一度ログアウト→再ログイン
```

### 4.2 プロジェクトディレクトリに移動
```bash
cd kitakyushu-waste-chatbot-enhanced

# ファイル確認
ls -la deploy-aws.sh docker-compose.aws.yml .env
```

### 4.3 自動デプロイ実行
```bash
# 一発デプロイ（全自動）
./deploy-aws.sh
```

### 4.4 デプロイプロセス確認
```
🚀 AWS環境デプロイを開始します...
✅ AWS環境をチェック中...
✅ 環境変数を設定中...
✅ SSL証明書を生成中...
✅ データディレクトリを準備中...
✅ Dockerイメージをビルド中...
✅ サービスを起動中...
✅ ヘルスチェックを実行中...
🎉 デプロイ完了!

📋 アクセス情報:
  Web UI: http://52.192.XXX.XXX
  HTTPS: https://52.192.XXX.XXX
  API: http://52.192.XXX.XXX:8000
```

---

## **🔍 ステップ5: デプロイ確認**

### 5.1 サービス状況確認
```bash
# コンテナ状況
docker-compose -f docker-compose.aws.yml ps

# 期待される出力:
NAME                    COMMAND                  SERVICE   STATUS    PORTS
kitakyushu-backend      "uvicorn backend.mai…"   backend   Up        0.0.0.0:8000->8000/tcp
kitakyushu-frontend     "streamlit run app_e…"   frontend  Up        0.0.0.0:8501->8501/tcp
kitakyushu-nginx        "/docker-entrypoint.…"   nginx     Up        0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
kitakyushu-ollama       "/bin/ollama serve"      ollama    Up        0.0.0.0:11434->11434/tcp
```

### 5.2 ログ確認
```bash
# 全サービスログ
docker-compose -f docker-compose.aws.yml logs -f

# 個別サービスログ
docker-compose -f docker-compose.aws.yml logs -f ollama    # LLMサービス
docker-compose -f docker-compose.aws.yml logs -f backend   # API
docker-compose -f docker-compose.aws.yml logs -f frontend  # Web UI
```

### 5.3 ヘルスチェック
```bash
# API エンドポイント確認
curl http://localhost:8000/api/search-info

# Web UI ヘルスチェック
curl http://localhost:8501/_stcore/health

# Nginx ヘルスチェック
curl http://localhost/health
```

---

## **🌐 ステップ6: ブラウザアクセス**

### 6.1 Web UIアクセス
1. ブラウザを開く
2. `http://YOUR_EC2_PUBLIC_IP` にアクセス
3. 初回アクセス時はOllamaモデルのダウンロード中のため、少し待機

### 6.2 動作確認
1. **ファイルアップロード**: CSVファイルをアップロード
2. **検索テスト**: 「ペットボトル」で検索
3. **チャット機能**: 質問を入力してレスポンス確認

---

## **⚠️ 重要な注意事項**

### 🕐 初回起動時間
- **Ollamaモデルダウンロード**: 15-30分
- **ChromaDBインデックス作成**: 5-10分
- **合計**: 約30-40分で完全稼働

### 💾 最小システム要件
- **RAM**: 8GB以上（推奨16GB）
- **ストレージ**: 20GB以上
- **CPU**: 2コア以上

### 🔒 セキュリティ
- HTTPSは自己署名証明書（本番では正式証明書推奨）
- APIエンドポイントは認証なし（必要に応じて追加）

---

## **🔧 管理・運用コマンド**

### サービス管理
```bash
# 再起動
docker-compose -f docker-compose.aws.yml restart

# 停止
docker-compose -f docker-compose.aws.yml down

# 起動
docker-compose -f docker-compose.aws.yml up -d

# 完全リセット（データ保持）
docker-compose -f docker-compose.aws.yml down
docker-compose -f docker-compose.aws.yml up -d

# 完全削除（データも削除）
docker-compose -f docker-compose.aws.yml down -v
```

### 監視
```bash
# リソース使用量
docker stats

# システムリソース
htop
free -h
df -h
```

---

## **🆘 トラブルシューティング**

### よくある問題と解決法

#### 1️⃣ GPU認識しない
```bash
# GPU確認
nvidia-smi

# CPU版に切り替え
sed 's/nvidia//g' docker-compose.aws.yml > docker-compose.cpu.yml
docker-compose -f docker-compose.cpu.yml up -d
```

#### 2️⃣ メモリ不足
```bash
# 軽量モデルに変更
echo 'LLM_MODEL=hf.co/mmnga/Llama-3.1-Swallow-8B-Instruct-v0.5-gguf:Q4_0' >> .env
docker-compose -f docker-compose.aws.yml restart
```

#### 3️⃣ ポートアクセスできない
```bash
# セキュリティグループ確認
# AWS EC2ダッシュボード → セキュリティグループ → インバウンドルール確認

# ローカルファイアウォール確認
sudo ufw status
sudo ufw allow 80
sudo ufw allow 443
```

#### 4️⃣ サービス起動失敗
```bash
# エラーログ確認
docker-compose -f docker-compose.aws.yml logs backend
docker-compose -f docker-compose.aws.yml logs frontend
docker-compose -f docker-compose.aws.yml logs ollama

# 個別サービス再起動
docker-compose -f docker-compose.aws.yml restart backend
```

---

## **💰 費用見積もり**

### 月額運用費用（東京リージョン）
```
t3.large (開発):     約$60/月
t3.xlarge (小規模):  約$120/月
g4dn.xlarge (GPU):   約$380/月

+ EBS gp3 30GB:      約$3/月
+ データ転送:        約$10-50/月
─────────────────────────────
合計: $73-433/月
```

### コスト削減のヒント
- **スポットインスタンス**使用で最大90%削減
- **自動停止スケジュール**設定
- **Reserved Instance**で1年契約割引

---

## **🎯 次のステップ**

1. **カスタムドメイン設定**
2. **Let's Encrypt SSL証明書**
3. **CloudWatch監視**
4. **Auto Scaling設定**
5. **RDS連携**（必要に応じて）

---

**🎉 これでAWS EC2での完全なデプロイが完了です！**

何か問題が発生した場合は、ログを確認して適切にトラブルシューティングを行ってください。
