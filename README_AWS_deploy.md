#  北九州市のゴミ捨て案内ChatBot

##  実際におこなったAWSでのデプロイ方法

-EC2でインスタンスを作成(セキュリティグループを編集し、フロント用ポート8002、バックエンド用ポート8000、Ollama用ポート11434を開放)
-.pemファイルを作成
-Elastic IPを作成して、インスタンスに適応させる
-ssh -i ".pemファイル名" ubuntu@ElasticIPでSSH接続
-sudo apt update && sudo apt upgrade -y
ollama run hf.co/mmnga/Llama-3.1-Swallow-8B-Instruct-v0.5-gguf
仮想環境作成
python3 -m venv chatbot_env
source chatbot_env/bin/activate
git clone https://github.com/Hisayuki04072/kitakyushu-waste-chatbot-enhanced.git
フロント、バックのrequirements.txtをダウンロード

# サービス有効化
sudo systemctl enable ollama

# サービス開始
sudo systemctl start ollama

-
sudo nano /etc/systemd/system/chatbot-backend.service

[Unit]
Description=Kitakyushu ChatBot Backend
After=network.target ollama.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/kitakyushu-waste-chatbot-enhanced
Environment=PATH=/home/ubuntu/chatbot_env/bin
Environment=PYTHONPATH=/home/ubuntu/kitakyushu-waste-chatbot-enhanced
ExecStart=/home/ubuntu/chatbot_env/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 300
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target

sudo nano /etc/systemd/system/chatbot-frontend.service

[Unit]
Description=Kitakyushu ChatBot Frontend
After=network.target chatbot-backend.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/kitakyushu-waste-chatbot-enhanced/frontend
Environment=PATH=/home/ubuntu/chatbot_env/bin
Environment=PYTHONPATH=/home/ubuntu/kitakyushu-waste-chatbot-enhanced
ExecStart=/home/ubuntu/chatbot_env/bin/streamlit run app_enhanced.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target

sudo apt update
sudo apt install -y nginx

sudo nano /etc/nginx/sites-available/chatbot

server {
    listen 80;
    server_name YOUR_EC2_PUBLIC_IP;
    client_max_body_size 100M;

    # ヘルスチェック
    location /health {
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }

    # フロントエンド（メイン）
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 86400;
    }

    # バックエンドAPI
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

sudo systemctl restart nginx
sudo systemctl enable nginx

# systemd設定リロード
sudo systemctl daemon-reload

# サービス有効化・起動
sudo systemctl enable chatbot-backend chatbot-frontend
sudo systemctl start chatbot-backend chatbot-frontend

uvicorn backend.main:app --host 0.0.0.0 --port 8000
streamlit run app_enhanced.py --server.port 8002 --server.address 0.0.0.0 
