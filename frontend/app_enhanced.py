"""
北九州市ごみ分別チャットボット - 高機能フロントエンド
要件定義対応版: FR-01〜FR-16, NFR-01〜NFR-05
"""

import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import base64
from io import BytesIO
import qrcode
import markdown
import bleach
import re

# JavaScriptコンポーネント読み込み
try:
    from enhanced_components import CHAT_JS_COMPONENT
except ImportError:
    CHAT_JS_COMPONENT = ""

# ページ設定
st.set_page_config(
    page_title="北九州市ごみ分別チャットボット",
    page_icon="♻️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 設定
BACKEND_URL = "http://localhost:8000/api"#バックエンドのURL、開いた場所によって変更する必要がある
CHAT_STREAM_URL = f"{BACKEND_URL}/chat/streaming"
CHAT_BLOCKING_URL = f"{BACKEND_URL}/chat/blocking"
UPLOAD_URL = f"{BACKEND_URL}/upload"

# セッション状態の初期化
def initialize_session():
    """セッション状態を初期化 (FR-13)"""
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "ui_state" not in st.session_state:
        st.session_state.ui_state = "initial"  # initial, chat
    
    if "is_first_interaction" not in st.session_state:
        st.session_state.is_first_interaction = True
    
    if "language" not in st.session_state:
        st.session_state.language = "ja"  # FR-12
    
    if "metrics" not in st.session_state:
        st.session_state.metrics = {
            "start_time": time.time(),
            "interactions": 0,
            "errors": 0,
            "total_response_time": 0,
            "successful_requests": 0
        }

initialize_session()

# 多言語対応 (FR-12)
TRANSLATIONS = {
    "ja": {
        "title": "北九州市ごみ分別チャットボット",
        "subtitle": "ごみの分別方法について何でもお聞きください",
        "placeholder": "例: アルミ缶はどう捨てればいいですか？",
        "send": "送信",
        "upload_csv": "CSVファイルをアップロード",
        "error_network": "ネットワークエラーが発生しました",
        "error_server": "サーバーエラーが発生しました",
        "retry": "再送信",
        "copy": "コピー",
        "edit": "編集",
        "thinking": "考え中...",
    },
    "en": {
        "title": "Kitakyushu Waste Sorting Chatbot",
        "subtitle": "Ask anything about waste sorting methods",
        "placeholder": "e.g. How should I dispose of aluminum cans?",
        "send": "Send",
        "upload_csv": "Upload CSV file",
        "error_network": "Network error occurred",
        "error_server": "Server error occurred", 
        "retry": "Retry",
        "copy": "Copy",
        "edit": "Edit",
        "thinking": "Thinking...",
    }
}

def t(key: str) -> str:
    """翻訳関数 (FR-12)"""
    return TRANSLATIONS.get(st.session_state.language, {}).get(key, key)

# カスタムCSS (FR-01, FR-03, FR-11)
def load_custom_css():
    """高機能UIのカスタムCSS"""
    css = """
    <style>
    /* ===== リセット & ベーススタイル ===== */
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        min-height: 100vh;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
    }
    
    /* Streamlitの余白調整 */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 100%;
    }
    
    /* ===== 初回表示の中央配置 (FR-01) ===== */
    .initial-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 60vh;
        text-align: center;
        padding: 2rem;
        animation: fadeIn 0.6s ease-out;
    }
    
    .initial-title {
        font-size: 2.5rem;
        font-weight: bold;
        color: white;
        margin-bottom: 1rem;
        text-shadow: 0 2px 8px rgba(0,0,0,0.3);
        background: linear-gradient(45deg, #fff, #e3f2fd);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .initial-subtitle {
        font-size: 1.2rem;
        color: rgba(255,255,255,0.9);
        margin-bottom: 2rem;
        text-shadow: 0 1px 3px rgba(0,0,0,0.3);
    }
    
    /* ===== チャット画面レイアウト (FR-02, FR-03) ===== */
    .chat-header {
        background: linear-gradient(90deg, #667eea, #764ba2);
        color: white;
        padding: 1rem 1.5rem;
        text-align: center;
        margin: -1rem -1rem 1rem -1rem;
        border-radius: 10px 10px 0 0;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    
    .chat-header h3 {
        margin: 0;
        font-weight: 600;
        text-shadow: 0 1px 3px rgba(0,0,0,0.3);
    }
    
    /* ===== メッセージスタイル ===== */
    .message {
        margin-bottom: 1.5rem;
        animation: messageSlide 0.3s ease-out;
        position: relative;
    }
    
    .message-bubble {
        padding: 1rem 1.5rem;
        border-radius: 20px;
        position: relative;
        word-wrap: break-word;
        max-width: 85%;
        line-height: 1.5;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    
    .message-bubble-user {
        background: linear-gradient(135deg, #007bff, #0056b3);
        color: white;
        margin-left: auto;
        border-bottom-right-radius: 8px;
    }
    
    .message-bubble-bot {
        background: #ffffff;
        color: #333;
        border: 1px solid #e9ecef;
        border-bottom-left-radius: 8px;
        margin-right: auto;
    }
    
    .message-system {
        text-align: center;
        margin: 1rem 0;
    }
    
    /* ===== メッセージアクション ===== */
    .message-actions {
        margin-top: 0.5rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.8rem;
        opacity: 0.7;
    }
    
    .message-actions button {
        background: none;
        border: none;
        cursor: pointer;
        padding: 0.2rem 0.4rem;
        border-radius: 4px;
        transition: background-color 0.2s ease;
    }
    
    .message-actions button:hover {
        background: rgba(0,0,0,0.1);
    }
    
    /* ===== コードブロック (FR-08, FR-09) ===== */
    .code-block-container {
        margin: 1rem 0;
        border-radius: 8px;
        overflow: hidden;
        background: #f8f9fa;
        border: 1px solid #e9ecef;
    }
    
    .code-block-header {
        background: #e9ecef;
        padding: 0.5rem 1rem;
        display: flex;
        justify-content: flex-end;
    }
    
    .copy-code-button {
        background: #6c757d;
        color: white;
        border: none;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-size: 0.8rem;
        cursor: pointer;
        transition: background-color 0.2s ease;
    }
    
    .copy-code-button:hover {
        background: #5a6268;
    }
    
    .code-block-container pre {
        margin: 0;
        padding: 1rem;
        overflow-x: auto;
        background: #f8f9fa;
    }
    
    .code-block-container code {
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        font-size: 0.9rem;
    }
    
    /* ===== 入力エリア固定表示 (FR-03, FR-11) ===== */
    .input-container {
        position: sticky;
        bottom: 0;
        background: white;
        padding: 1rem 0;
        border-top: 1px solid #e0e0e0;
        z-index: 100;
        backdrop-filter: blur(10px);
        background: rgba(255,255,255,0.95);
    }
    
    /* ===== エラー表示 (FR-06) ===== */
    .error-message {
        background: linear-gradient(45deg, #fff3cd, #ffeaa7);
        border: 1px solid #ffeaa7;
        color: #856404;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    
    .retry-button {
        background: linear-gradient(45deg, #ffc107, #e0a800);
        color: #000;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        cursor: pointer;
        margin-top: 0.5rem;
        font-weight: 500;
        transition: all 0.2s ease;
    }
    
    .retry-button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    /* ===== モバイル対応 (FR-11) ===== */
    @media (max-width: 768px) {
        .initial-title { 
            font-size: 2rem; 
        }
        
        .message-bubble { 
            max-width: 90%; 
            padding: 0.8rem 1rem;
        }
        
        .input-container { 
            padding: 0.5rem 0; 
        }
        
        .chat-header {
            margin: -1rem -0.5rem 1rem -0.5rem;
        }
    }
    
    /* ===== iOS Safari対応 ===== */
    @supports (padding: max(0px)) {
        .input-container {
            padding-bottom: max(1rem, env(safe-area-inset-bottom));
        }
    }
    
    /* ===== アニメーション ===== */
    @keyframes fadeIn {
        from { 
            opacity: 0; 
            transform: translateY(20px); 
        }
        to { 
            opacity: 1; 
            transform: translateY(0); 
        }
    }
    
    @keyframes messageSlide {
        from { 
            opacity: 0; 
            transform: translateX(-20px); 
        }
        to { 
            opacity: 1; 
            transform: translateX(0); 
        }
    }
    
    @keyframes slideUp {
        from { transform: translateY(100%); }
        to { transform: translateY(0); }
    }
    
    /* ===== ストリーミング表示用 (FR-04) ===== */
    .typing-indicator {
        display: inline-block;
        color: #999;
    }
    
    .typing-indicator::after {
        content: '●●●';
        animation: typing 1.5s infinite;
    }
    
    @keyframes typing {
        0%, 60%, 100% { 
            opacity: 0.4; 
        }
        30% { 
            opacity: 1; 
        }
    }
    
    /* ===== アクセシビリティ (FR-16) ===== */
    .sr-only {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border: 0;
    }
    
    /* フォーカス表示 */
    *:focus {
        outline: 2px solid #007bff;
        outline-offset: 2px;
    }
    
    /* ハイコントラストモード対応 */
    @media (prefers-contrast: high) {
        .message-bubble-user {
            background: #000 !important;
            color: #fff !important;
            border: 2px solid #fff;
        }
        
        .message-bubble-bot {
            background: #fff !important;
            color: #000 !important;
            border: 2px solid #000;
        }
    }
    
    /* ダークモード対応 */
    @media (prefers-color-scheme: dark) {
        .stApp {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        }
        
        .message-bubble-bot {
            background: #2d3748;
            color: #e2e8f0;
            border-color: #4a5568;
        }
        
        .chat-header {
            background: linear-gradient(90deg, #2d3748, #4a5568);
        }
    }
    
    /* アニメーション無効化（アクセシビリティ） */
    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
        }
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# JavaScript関数 (FR-05, FR-10)
def load_custom_js():
    """高機能インタラクションのJavaScript"""
    if CHAT_JS_COMPONENT:
        components.html(CHAT_JS_COMPONENT, height=0)
    else:
        # フォールバック用の基本JavaScript
        basic_js = """
        <script>
        function sendMessage() {
            const inputField = document.querySelector('.input-field');
            if (inputField && inputField.value.trim()) {
                window.parent.postMessage({
                    type: 'streamlit_send_message',
                    message: inputField.value.trim()
                }, '*');
                inputField.value = '';
            }
        }
        
        function copyMessage(messageId) {
            const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
            if (messageElement) {
                navigator.clipboard.writeText(messageElement.textContent)
                    .then(() => alert('コピーしました'))
                    .catch(() => alert('コピーに失敗しました'));
            }
        }
        
        function copyCodeBlock(codeId) {
            const codeElement = document.getElementById(codeId);
            if (codeElement) {
                navigator.clipboard.writeText(codeElement.textContent)
                    .then(() => alert('コードをコピーしました'))
                    .catch(() => alert('コピーに失敗しました'));
            }
        }
        </script>
        """
        components.html(basic_js, height=0)

# メッセージ管理
class MessageManager:
    """メッセージ管理クラス (FR-13)"""
    
    @staticmethod
    def add_message(role: str, content: str, message_id: str = None) -> str:
        """メッセージを追加"""
        if message_id is None:
            message_id = str(uuid.uuid4())
        
        print(f"[DEBUG] MessageManager.add_message: role='{role}', content_length={len(content)}, id={message_id}")#
        
        message = {
            "id": message_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "session_id": st.session_state.session_id
        }
        
        st.session_state.messages.append(message)
        print(f"[DEBUG] メッセージ追加完了。総メッセージ数: {len(st.session_state.messages)}")#
        
        return message_id
    
    @staticmethod
    def get_messages() -> List[Dict]:
        """メッセージ履歴を取得"""
        return st.session_state.messages
    
    @staticmethod
    def edit_message(message_id: str, new_content: str) -> bool:
        """メッセージを編集 (FR-07)"""
        for message in st.session_state.messages:
            if message["id"] == message_id:
                message["content"] = new_content
                message["edited"] = True
                message["edit_timestamp"] = datetime.now().isoformat()
                return True
        return False

# API通信
class APIClient:
    """API通信クラス (FR-06, FR-15)"""
    
    @staticmethod
    def send_message(message: str) -> Dict[str, Any]:
        """メッセージをAPIに送信"""
        print(f"[DEBUG] APIClient.send_message 開始: message='{message}'")#
        start_time = time.time()
        
        try:
            payload = {"prompt": message}#
            print(f"[DEBUG] 送信ペイロード: {payload}")#
            print(f"[DEBUG] 送信先URL: {CHAT_BLOCKING_URL}")#
            
            response = requests.post(
                CHAT_BLOCKING_URL,
                json=payload,  # messageからpromptに修正#
                timeout=300,  # 120秒から300秒（5分）に延長
                headers={"Content-Type": "application/json"}
            )
            
            response_time = time.time() - start_time
            print(f"[DEBUG] HTTPレスポンス受信: status_code={response.status_code}, 時間={response_time:.2f}秒")#
            
            # メトリクス更新 (FR-15)
            st.session_state.metrics["total_response_time"] += response_time
            st.session_state.metrics["interactions"] += 1
            
            if response.status_code == 200:
                st.session_state.metrics["successful_requests"] += 1
                response_data = response.json()#
                print(f"[DEBUG] JSON解析成功: keys={list(response_data.keys())}")#
                
                return {
                    "success": True,
                    "data": response_data,#
                    "response_time": response_time
                }
            else:
                st.session_state.metrics["errors"] += 1
                print(f"[DEBUG] HTTPエラー: {response.status_code}")#
                
                # エラーレスポンスの詳細を取得
                try:
                    error_detail = response.json()
                    error_msg = error_detail.get("detail", f"HTTP {response.status_code}")
                    print(f"[DEBUG] エラー詳細: {error_detail}")#
                except Exception as json_error:#
                    error_msg = f"HTTP {response.status_code}"
                    print(f"[DEBUG] JSON解析エラー: {json_error}")#
                    
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                    "response_time": response_time
                }
                
        except requests.exceptions.RequestException as e:
            st.session_state.metrics["errors"] += 1
            error_msg = f"Network error: {str(e)}"#
            print(f"[DEBUG] ネットワークエラー: {error_msg}")#
            
            return {
                "success": False,
                "error": error_msg,#
                "response_time": time.time() - start_time
            }

# UI Components
def render_initial_screen():
    """初回表示画面 (FR-01)"""
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown(f"""
        <div class="initial-container">
            <div class="initial-title">{t("title")}</div>
            <div class="initial-subtitle">{t("subtitle")}</div>
        </div>
        """, unsafe_allow_html=True)
        
        # 初回入力欄
        user_input = st.text_area(
            label="ユーザー入力",
            placeholder=t("placeholder"),
            key="chat_input",
            height=100,
            label_visibility="collapsed"
        )
        
        col_a, col_b, col_c = st.columns([2, 1, 2])
        with col_b:
            st.button(t("send"), key="send_initial", use_container_width=True)

def render_chat_interface():
    """チャット画面 (FR-02, FR-03, FR-04)"""
    # チャットヘッダー
    st.markdown(f"""
    <div class="chat-header">
        <h3>{t("title")}</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # メッセージ表示エリア
    messages_container = st.container()
    with messages_container:
        render_messages()
    
    # 固定入力エリア (FR-03)
    
    # 入力欄
    user_input = st.text_area(
        label="メッセージ入力",
        placeholder=t("placeholder"),
        key="chat_input_main",
        height=60,
        label_visibility="collapsed"
    )
    
    # 送信ボタン
    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        send_button = st.button(t("send"), key="send_chat")
    with col3:
        if st.button("🔄", key="clear_chat", help="チャットをクリア"):
            st.session_state.messages = []
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)

def render_messages():
    """メッセージ一覧をレンダリング (FR-08, FR-09)"""
    messages = MessageManager.get_messages()
    
    for i, message in enumerate(messages):
        role = message["role"]
        content = message["content"]
        message_id = message["id"]
        timestamp = message.get("timestamp", "")
        
        # メッセージコンテナ
        if role == "user":
            # ユーザーメッセージ（右寄せ）
            col1, col2 = st.columns([1, 4])
            with col2:
                with st.container():
                    st.markdown(f"""
                    <div class="message message-user" data-message-id="{message_id}">
                        <div class="message-bubble message-bubble-user">
                            {content}
                            <div class="message-actions">
                                <small>{format_timestamp(timestamp)}</small>
                                <button onclick="copyMessage('{message_id}')" title="{t('copy')}">📋</button>
                                <button onclick="editMessage('{message_id}')" title="{t('edit')}">✏️</button>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
        elif role == "assistant":
            # AIメッセージ（左寄せ）
            col1, col2 = st.columns([4, 1])
            with col1:
                with st.container():
                    # プレーンテキスト表示（HTMLを含まないように）
                    clean_content = content.strip()
                    
                    st.markdown(f"""
                    <div class="message message-bot" data-message-id="{message_id}">
                        <div class="message-bubble message-bubble-bot">
                            <div class="message-content">
                                {sanitize_content(clean_content.replace('\n', '<br>'))}
                            </div>
                            <div class="message-actions">
                                <small>{format_timestamp(timestamp)}</small>
                                <button onclick="copyMessage('{message_id}')" title="{t('copy')}">📋</button>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
        elif role == "system":
            # システムメッセージ（エラーなど）
            st.markdown(f"""
            <div class="message message-system">
                {content}
            </div>
            """, unsafe_allow_html=True)

def format_timestamp(timestamp_str: str) -> str:
    """タイムスタンプをフォーマット"""
    try:
        if not timestamp_str:
            return ""
        
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        
        # 今日の場合は時刻のみ
        if dt.date() == now.date():
            return dt.strftime("%H:%M")
        else:
            return dt.strftime("%m/%d %H:%M")
            
    except Exception:
        return ""

def sanitize_content(content: str) -> str:
    """コンテンツをサニタイズ (FR-14)"""
    # 許可するHTMLタグと属性
    allowed_tags = [
        'p', 'br', 'strong', 'em', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'blockquote', 'a', 'div', 'span'
    ]
    
    allowed_attributes = {
        'a': ['href', 'title', 'target', 'rel'],
        'div': ['class'],
        'span': ['class'],
        'code': ['class'],
        'pre': ['class']
    }
    
    # リンクの安全な処理
    def set_link_attributes(tag, name, value):
        if name == 'href':
            if not value.startswith(('http://', 'https://', 'mailto:')):
                return False
            # target="_blank"とrel="noopener"を追加 (FR-14)
            tag['target'] = '_blank'
            tag['rel'] = 'noopener noreferrer'
        return True
    
    return bleach.clean(
        content,
        tags=allowed_tags,
        attributes=allowed_attributes,
        protocols=['http', 'https', 'mailto'],
        strip=True
    )

def format_markdown(content: str) -> str:
    """Markdownフォーマット (FR-08)"""
    try:
        # Markdownを HTML に変換
        html_content = markdown.markdown(
            content,
            extensions=[
                'codehilite',
                'fenced_code', 
                'tables',
                'toc'
            ],
            extension_configs={
                'codehilite': {
                    'css_class': 'highlight',
                    'use_pygments': True
                }
            }
        )
        
        # サニタイズ
        safe_html = sanitize_content(html_content)
        
        # コードブロックにコピーボタンを追加 (FR-09)
        safe_html = add_copy_buttons_to_code(safe_html)
        
        return safe_html
        
    except Exception as e:
        st.error(f"Markdown処理エラー: {str(e)}")
        # フォールバック: プレーンテキストとして表示
        return sanitize_content(content.replace('\n', '<br>'))

def add_copy_buttons_to_code(html_content: str) -> str:
    """コードブロックにコピーボタンを追加 (FR-09)"""
    def add_copy_button(match):
        code_content = match.group(2)
        code_id = f"code_{uuid.uuid4().hex[:8]}"
        
        return f"""
        <div class="code-block-container">
            <div class="code-block-header">
                <button class="copy-code-button" onclick="copyCodeBlock('{code_id}')" 
                        aria-label="コードをコピー">
                    📋 {t('copy')}
                </button>
            </div>
            <pre id="{code_id}"><code{match.group(1)}>{code_content}</code></pre>
        </div>
        """
    
    # コードブロックパターンをマッチして置換
    pattern = r'<pre><code([^>]*)>(.*?)</code></pre>'
    return re.sub(pattern, add_copy_button, html_content, flags=re.DOTALL)

def render_edit_button(message: Dict) -> str:
    """編集ボタンをレンダリング (FR-07)"""
    if message["role"] == "user":
        return f"""
        <button onclick="editMessage('{message['id']}')" aria-label="{t('edit')}" title="{t('edit')}">
            ✏️
        </button>
        """
    return ""

# メイン処理
def main():
    """メインアプリケーション"""
    load_custom_css()
    load_custom_js()
    
    # サイドバー設定
    with st.sidebar:
        # 言語切替 (FR-12)
        language_options = {"ja": "🇯🇵 日本語", "en": "🇺🇸 English"}
        selected_language = st.selectbox(
            "Language / 言語",
            options=list(language_options.keys()),
            format_func=lambda x: language_options[x],
            key="language"
        )
        
        st.divider()
        
        # CSV アップロード
        st.subheader("📁 " + t("upload_csv"))
        uploaded_file = st.file_uploader(
            "CSVファイル選択",
            type=['csv'],
            help="ごみ分別データのCSVファイルをアップロードできます",
            label_visibility="collapsed"
        )
        
        if uploaded_file:
            upload_csv_file(uploaded_file)
        
        st.divider()
        
        # QRコード生成
        if st.button("📱 QRコード生成"):
            generate_qr_code()
        
        st.divider()
        
        # 統計情報表示 (FR-15)
        if st.session_state.metrics["interactions"] > 0:
            st.subheader("📊 統計情報")
            
            # 平均応答時間
            if st.session_state.metrics["successful_requests"] > 0:
                avg_response_time = (
                    st.session_state.metrics["total_response_time"] / 
                    st.session_state.metrics["successful_requests"]
                )
                st.metric("平均応答時間", f"{avg_response_time:.2f}s")
            
            # 成功率
            success_rate = (
                st.session_state.metrics["successful_requests"] / 
                st.session_state.metrics["interactions"] * 100
            )
            st.metric("成功率", f"{success_rate:.1f}%")
            
            # エラー率
            error_rate = (
                st.session_state.metrics["errors"] / 
                st.session_state.metrics["interactions"] * 100
            )
            st.metric("エラー率", f"{error_rate:.1f}%")
            
            # インタラクション数
            st.metric("総会話数", st.session_state.metrics["interactions"])
            
            # 初回インタラクション時間
            if "first_interaction_time" in st.session_state.metrics:
                st.metric(
                    "初回応答までの時間",
                    f"{st.session_state.metrics['first_interaction_time']:.2f}s"
                )
            
            # セッション時間
            session_duration = time.time() - st.session_state.metrics["start_time"]
            st.metric("セッション時間", f"{session_duration/60:.1f}分")
        
        st.divider()
        
        # 設定
        st.subheader("⚙️ 設定")
        
        # テーマ切替
        if st.checkbox("ハイコントラストモード", key="high_contrast"):
            st.markdown(
                '<style>body { filter: contrast(150%) brightness(120%); }</style>',
                unsafe_allow_html=True
            )
        
        # アニメーション無効化
        if st.checkbox("アニメーション無効", key="reduce_motion"):
            st.markdown(
                '<style>*, *::before, *::after { animation: none !important; transition: none !important; }</style>',
                unsafe_allow_html=True
            )
        
        # チャット履歴クリア
        if st.button("🗑️ チャット履歴をクリア", type="secondary"):
            st.session_state.messages = []
            st.rerun()
    
    # メッセージ処理（一箇所でのみ処理）
    handle_message_input()
    
    # メインUI
    if st.session_state.ui_state == "initial":
        render_initial_screen()
    else:
        render_chat_interface()
    
    # パフォーマンス監視 (FR-15, NFR-01)
    if st.session_state.metrics["interactions"] == 0:
        # 初回ロード時間の記録
        st.session_state.metrics["load_complete_time"] = time.time()

def generate_qr_code():
    """QRコード生成機能"""
    try:
        # 現在のURL（モバイルアクセス用）
        base_url = "http://localhost:8002"  # 高機能UI用ポート#UIを開いた場所にポート番号を変更する
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(base_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # QRコードをbase64エンコード
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode()
        
        st.markdown(f"""
        <div style="text-align: center; padding: 1rem;">
            <p>スマートフォンでアクセス:</p>
            <img src="data:image/png;base64,{img_str}" style="max-width: 200px;">
            <p style="font-size: 0.8em; margin-top: 0.5rem;">{base_url}</p>
        </div>
        """, unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"QRコード生成エラー: {str(e)}")

def handle_message_input():
    """メッセージ入力処理 - 単一入力ソース検出"""
    print("[DEBUG] handle_message_input 開始")
    
    # チャット入力の処理（単一メッセージ検出）
    user_message = None
    input_source = None
    
    # 各入力ソースを個別にチェックし、最初に見つかったもののみ処理
    
    # 1. 初回画面: 送信ボタンが押された場合（優先度最高）
    if st.session_state.get("send_initial", False):
        user_message = st.session_state.get("chat_input", "").strip()
        input_source = "send_initial"
        print(f"[DEBUG] send_initial検出: message='{user_message}'")
        if user_message:
            st.session_state.chat_input = ""
    
    # 2. チャット画面: 送信ボタンが押された場合（優先度高）
    elif st.session_state.get("send_chat", False):
        user_message = st.session_state.get("chat_input_main", "").strip()
        input_source = "send_chat"
        print(f"[DEBUG] send_chat検出: message='{user_message}'")
        if user_message:
            st.session_state.chat_input_main = ""
    
    # 5. JavaScript からのメッセージ（最低優先度）
    elif hasattr(st.session_state, '_js_message'):
        user_message = st.session_state._js_message
        input_source = "_js_message"
        print(f"[DEBUG] _js_message検出: message='{user_message}'")
        delattr(st.session_state, '_js_message')

    # メッセージがある場合のみ処理
    if user_message:
        print(f"[DEBUG] 処理するメッセージ: '{user_message}' (入力元: {input_source})")
        
        # 初回送信時の画面遷移 (FR-02)
        if st.session_state.ui_state == "initial":
            print("[DEBUG] UI状態を 'initial' から 'chat' に変更")
            st.session_state.ui_state = "chat"
        
        # メッセージ処理を実行
        process_user_message(user_message)
    else:
        print("[DEBUG] 処理するメッセージなし")

def process_user_message(message: str):
    """ユーザーメッセージを処理"""
    # デバッグ: 関数開始
    print(f"[DEBUG] process_user_message 開始: message='{message}'")#
    
    if not message.strip():
        print("[DEBUG] 空のメッセージのため処理をスキップ")
        return
    
    # メトリクス更新 (FR-15)
    st.session_state.metrics["interactions"] += 1
    print(f"[DEBUG] インタラクション数を更新: {st.session_state.metrics['interactions']}")#
    
    # ユーザーメッセージを追加
    user_msg_id = MessageManager.add_message("user", message)
    print(f"[DEBUG] ユーザーメッセージ追加完了: ID={user_msg_id}")#
    
    # 入力時間を記録
    if st.session_state.is_first_interaction:
        interaction_time = time.time() - st.session_state.metrics["start_time"]
        st.session_state.metrics["first_interaction_time"] = interaction_time
        st.session_state.is_first_interaction = False
        print(f"[DEBUG] 初回インタラクション時間記録: {interaction_time:.2f}秒")#
    
    # AIレスポンスを取得
    start_time = time.time()
    print(f"[DEBUG] API呼び出し開始: URL={CHAT_BLOCKING_URL}")#
    
    with st.spinner(t("thinking")):
        result = APIClient.send_message(message)
    
    response_time = time.time() - start_time
    print(f"[DEBUG] API呼び出し完了: レスポンス時間={response_time:.2f}秒")#
    print(f"[DEBUG] API結果: success={result.get('success')}")#
    
    if result["success"]:
        response_content = result["data"].get("response", "")
        print(f"[DEBUG] 受信したレスポンス長: {len(response_content)}文字")#
        print(f"[DEBUG] レスポンス内容（最初の100文字）: {response_content[:100]}...")#
        
        # HTMLタグを除去（特にmessage-actionsなど）
        import re
        # HTMLタグ全体を除去
        clean_content = re.sub(r'<[^>]+>', '', response_content)
        # 余計な空白を整理
        clean_content = re.sub(r'\s+', ' ', clean_content).strip()
        
        print(f"[DEBUG] クリーン後のコンテンツ長: {len(clean_content)}文字")#
        print(f"[DEBUG] クリーン後の内容（最初の100文字）: {clean_content[:100]}...")#
        
        MessageManager.add_message("assistant", clean_content)
        print("[DEBUG] AIレスポンスメッセージ追加完了")
        
        # 成功メトリクス
        st.session_state.metrics["successful_requests"] += 1
        st.session_state.metrics["total_response_time"] += response_time
        print(f"[DEBUG] 成功メトリクス更新: 成功リクエスト数={st.session_state.metrics['successful_requests']}")#
        
    else:
        # エラー処理 (FR-06)
        st.session_state.metrics["errors"] += 1
        error_msg = result.get('error', 'Unknown error')#
        print(f"[DEBUG] API呼び出しエラー: {error_msg}")#
        
        error_message = create_error_message(error_msg, message)#
        MessageManager.add_message("system", error_message)
        print("[DEBUG] エラーメッセージ追加完了")
    
    print(f"[DEBUG] 現在のメッセージ総数: {len(st.session_state.messages)}")#
    print("[DEBUG] st.rerun() を実行します")
    
    # メッセージを追加した後、画面を更新
    st.rerun()

def create_error_message(error: str, original_message: str) -> str:
    """エラーメッセージを生成 (FR-06)"""
    return f"""
    <div class="error-message">
        <strong>{t('error_server')}</strong><br>
        {error}<br>
        <button class="retry-button" onclick="retryMessage('{original_message}')">
            {t('retry')}
        </button>
    </div>
    """

def upload_csv_file(uploaded_file):
    """CSVファイルアップロード処理"""
    try:
        # ファイルサイズ表示
        file_size = len(uploaded_file.getvalue())
        st.info(f"📁 ファイルサイズ: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
        
        # プログレスバー表示
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text("📤 ファイルをアップロード中...")
        progress_bar.progress(25)
        
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "text/csv")}
        
        # タイムアウトを10分（600秒）に延長
        status_text.text("⚙️ サーバーで処理中（最大10分）...")
        progress_bar.progress(50)
        
        response = requests.post(UPLOAD_URL, files=files, timeout=600)
        
        progress_bar.progress(75)
        status_text.text("✅ レスポンス処理中...")
        
        if response.status_code == 200:
            progress_bar.progress(100)
            result = response.json()
            ingested_count = result.get("ingested", 0)
            st.success(f"✅ {uploaded_file.name} をアップロードしました（{ingested_count} 件のデータを追加）")
            status_text.empty()
            progress_bar.empty()
        else:
            progress_bar.empty()
            status_text.empty()
            try:
                error_detail = response.json().get("detail", "不明なエラー")
                st.error(f"❌ アップロードエラー (HTTP {response.status_code}): {error_detail}")
            except:
                st.error(f"❌ アップロードエラー: HTTP {response.status_code}")
                
    except requests.exceptions.Timeout:
        st.error("❌ タイムアウトエラー: ファイルの処理に時間がかかりすぎました（10分以上）。ファイルサイズを小さくして再試行してください。")
    except requests.exceptions.ConnectionError:
        st.error("❌ 接続エラー: バックエンドサーバーに接続できません。サーバーが起動しているか確認してください。")
    except Exception as e:
        st.error(f"❌ アップロードエラー: {str(e)}")
        print(f"[DEBUG] CSV upload error: {e}")

if __name__ == "__main__":
    main()
