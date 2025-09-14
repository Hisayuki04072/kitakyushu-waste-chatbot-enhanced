"""
高機能チャットUI JavaScript コンポーネント
FR-05, FR-10, FR-11, FR-15対応
"""

CHAT_JS_COMPONENT = """
<script>
// グローバル変数
let isComposing = false;
let autoScrollEnabled = true;
let messageQueue = [];
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
let metrics = {
    startTime: Date.now(),
    interactions: 0,
    inputFocusTime: null,
    errors: 0,
    totalResponseTime: 0
};

// メッセージ送信制御 (FR-05)
class InputController {
    constructor() {
        this.setupEventListeners();
        this.initializeAutoResize();
    }
    
    setupEventListeners() {
        const inputField = document.querySelector('.input-field');
        if (!inputField) return;
        
        // IME対応
        inputField.addEventListener('compositionstart', () => {
            isComposing = true;
        });
        
        inputField.addEventListener('compositionend', () => {
            isComposing = false;
        });
        
        // キーボード制御
        inputField.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
                e.preventDefault();
                this.sendMessage();
            }
            
            // ショートカットキー (FR-16)
            if (e.ctrlKey || e.metaKey) {
                switch(e.key) {
                    case 'Enter':
                        e.preventDefault();
                        this.sendMessage();
                        break;
                    case 'k':
                        e.preventDefault();
                        this.clearChat();
                        break;
                }
            }
        });
        
        // フォーカス時間測定 (FR-15)
        inputField.addEventListener('focus', () => {
            if (metrics.inputFocusTime === null) {
                metrics.inputFocusTime = Date.now();
            }
        });
        
        inputField.addEventListener('blur', () => {
            if (metrics.inputFocusTime) {
                const focusTime = Date.now() - metrics.inputFocusTime;
                this.sendMetrics('input_focus_time', focusTime);
                metrics.inputFocusTime = null;
            }
        });
    }
    
    initializeAutoResize() {
        const inputField = document.querySelector('.input-field');
        if (!inputField) return;
        
        inputField.addEventListener('input', () => {
            inputField.style.height = 'auto';
            const newHeight = Math.min(inputField.scrollHeight, 120);
            inputField.style.height = newHeight + 'px';
            
            // 入力エリア調整時のスクロール位置維持
            this.maintainScrollPosition();
        });
    }
    
    sendMessage() {
        const inputField = document.querySelector('.input-field');
        const message = inputField.value.trim();
        
        if (!message) return;
        
        // 送信ボタン無効化
        const sendButton = document.querySelector('.send-button');
        if (sendButton) {
            sendButton.disabled = true;
            sendButton.innerHTML = '⏳';
        }
        
        // メトリクス更新
        metrics.interactions++;
        const requestStartTime = Date.now();
        
        // Streamlitに送信
        window.parent.postMessage({
            type: 'streamlit_send_message',
            message: message,
            sessionId: this.getSessionId(),
            timestamp: requestStartTime
        }, '*');
        
        // 入力欄クリア & リセット
        inputField.value = '';
        inputField.style.height = 'auto';
        
        // 送信後の処理
        setTimeout(() => {
            if (sendButton) {
                sendButton.disabled = false;
                sendButton.innerHTML = '▶️';
            }
        }, 500);
    }
    
    maintainScrollPosition() {
        const messagesContainer = document.querySelector('.messages-container');
        if (messagesContainer && autoScrollEnabled) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }
    
    clearChat() {
        window.parent.postMessage({
            type: 'streamlit_clear_chat'
        }, '*');
    }
    
    getSessionId() {
        return sessionStorage.getItem('chatSessionId') || 
               (() => {
                   const id = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
                   sessionStorage.setItem('chatSessionId', id);
                   return id;
               })();
    }
    
    sendMetrics(type, data) {
        window.parent.postMessage({
            type: 'streamlit_metrics',
            metricType: type,
            data: data,
            timestamp: Date.now()
        }, '*');
    }
}

// 自動スクロール制御 (FR-10)
class ScrollController {
    constructor() {
        this.isUserScrolling = false;
        this.scrollTimeout = null;
        this.setupScrollHandling();
    }
    
    setupScrollHandling() {
        const messagesContainer = document.querySelector('.messages-container');
        if (!messagesContainer) return;
        
        messagesContainer.addEventListener('scroll', () => {
            this.isUserScrolling = true;
            
            clearTimeout(this.scrollTimeout);
            this.scrollTimeout = setTimeout(() => {
                this.isUserScrolling = false;
            }, 1000);
            
            // 最下部近くにいる場合は自動スクロール有効
            const threshold = 100;
            const isNearBottom = messagesContainer.scrollTop >= 
                messagesContainer.scrollHeight - messagesContainer.clientHeight - threshold;
            
            autoScrollEnabled = isNearBottom;
        });
        
        // 新しいメッセージ到着時の自動スクロール
        this.observeNewMessages();
    }
    
    observeNewMessages() {
        const messagesContainer = document.querySelector('.messages-container');
        if (!messagesContainer) return;
        
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                    if (autoScrollEnabled && !this.isUserScrolling) {
                        this.smoothScrollToBottom();
                    }
                }
            });
        });
        
        observer.observe(messagesContainer, {
            childList: true,
            subtree: true
        });
    }
    
    smoothScrollToBottom() {
        const messagesContainer = document.querySelector('.messages-container');
        if (messagesContainer) {
            messagesContainer.scrollTo({
                top: messagesContainer.scrollHeight,
                behavior: 'smooth'
            });
        }
    }
                   const id = 'session_' + Date.now() + '_
    
    scrollToMessage(messageId) {
        const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        if (messageElement) {
            messageElement.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });
        }
    }
}

// ストリーミング表示 (FR-04)
class StreamingController {
    constructor() {
        this.currentStreamId = null;
        this.streamBuffer = '';
        this.reconnectInterval = 1000;
    }
    
    startStreaming(endpoint, messageId) {
        if (this.currentStreamId) {
            this.stopStreaming();
        }
        
        this.currentStreamId = messageId;
        this.streamBuffer = '';
        
        // Server-Sent Events接続
        const eventSource = new EventSource(endpoint);
        
        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleStreamData(data);
            } catch (e) {
                console.error('Stream parsing error:', e);
            }
        };
        
        eventSource.onerror = (error) => {
            console.error('Stream error:', error);
            this.handleStreamError();
            eventSource.close();
        };
        
        eventSource.onopen = () => {
            reconnectAttempts = 0;
        };
        
        return eventSource;
    }
    
    handleStreamData(data) {
        if (data.type === 'content') {
            this.streamBuffer += data.content;
            this.updateStreamingMessage(this.streamBuffer);
        } else if (data.type === 'complete') {
            this.completeStreaming();
        } else if (data.type === 'error') {
            this.handleStreamError(data.error);
        }
    }
    
    updateStreamingMessage(content) {
        const messageElement = document.querySelector(`[data-message-id="${this.currentStreamId}"]`);
        if (messageElement) {
            const contentElement = messageElement.querySelector('.message-content');
            if (contentElement) {
                contentElement.innerHTML = this.formatContent(content) + 
                    '<span class="typing-indicator"></span>';
            }
        }
    }
    
    completeStreaming() {
        const messageElement = document.querySelector(`[data-message-id="${this.currentStreamId}"]`);
        if (messageElement) {
            const typingIndicator = messageElement.querySelector('.typing-indicator');
            if (typingIndicator) {
                typingIndicator.remove();
            }
        }
        this.currentStreamId = null;
        this.streamBuffer = '';
    }
    
    handleStreamError(error = null) {
        if (reconnectAttempts < maxReconnectAttempts) {
            setTimeout(() => {
                this.reconnectStream();
            }, this.reconnectInterval * Math.pow(2, reconnectAttempts));
            reconnectAttempts++;
        } else {
            this.showStreamError(error);
        }
    }
    
    reconnectStream() {
        // 再接続ロジック
        window.parent.postMessage({
            type: 'streamlit_reconnect_stream',
            messageId: this.currentStreamId
        }, '*');
    }
    
    showStreamError(error) {
        const messageElement = document.querySelector(`[data-message-id="${this.currentStreamId}"]`);
        if (messageElement) {
            const contentElement = messageElement.querySelector('.message-content');
            if (contentElement) {
                contentElement.innerHTML = `
                    <div class="error-message">
                        ストリーミング接続でエラーが発生しました。
                        ${error ? ': ' + error : ''}
                        <button onclick="retryStreaming('${this.currentStreamId}')">再試行</button>
                    </div>
                `;
            }
        }
    }
    
    formatContent(content) {
        // 基本的なMarkdown対応
        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }
}

// クリップボード機能 (FR-09)
class ClipboardController {
    static async copyText(text, buttonElement = null) {
        try {
            await navigator.clipboard.writeText(text);
            this.showCopyFeedback(buttonElement, true);
            
            // メトリクス記録
            window.parent.postMessage({
                type: 'streamlit_metrics',
                metricType: 'copy_action',
                data: { success: true, textLength: text.length }
            }, '*');
            
        } catch (err) {
            console.error('Copy failed:', err);
            this.fallbackCopy(text);
            this.showCopyFeedback(buttonElement, false);
        }
    }
    
    static fallbackCopy(text) {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.select();
        
        try {
            document.execCommand('copy');
        } catch (err) {
            console.error('Fallback copy failed:', err);
        }
        
        document.body.removeChild(textArea);
    }
    
    static showCopyFeedback(buttonElement, success) {
        if (buttonElement) {
            const originalText = buttonElement.innerHTML;
            buttonElement.innerHTML = success ? '✅' : '❌';
            buttonElement.disabled = true;
            
            setTimeout(() => {
                buttonElement.innerHTML = originalText;
                buttonElement.disabled = false;
            }, 2000);
        }
    }
}

// エラー処理とトースト通知 (FR-06)
class NotificationController {
    static show(message, type = 'info', duration = 5000) {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <span class="notification-message">${message}</span>
                <button class="notification-close" onclick="this.parentElement.parentElement.remove()">×</button>
            </div>
        `;
        
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            min-width: 300px;
            max-width: 500px;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            transform: translateX(100%);
            transition: transform 0.3s ease;
            ${this.getNotificationStyles(type)}
        `;
        
        document.body.appendChild(notification);
        
        // アニメーション
        setTimeout(() => {
            notification.style.transform = 'translateX(0)';
        }, 100);
        
        // 自動削除
        if (duration > 0) {
            setTimeout(() => {
                notification.style.transform = 'translateX(100%)';
                setTimeout(() => {
                    if (notification.parentElement) {
                        notification.remove();
                    }
                }, 300);
            }, duration);
        }
    }
    
    static getNotificationStyles(type) {
        const styles = {
            info: 'background: #e3f2fd; color: #1565c0; border-left: 4px solid #2196f3;',
            success: 'background: #e8f5e8; color: #2e7d32; border-left: 4px solid #4caf50;',
            warning: 'background: #fff3e0; color: #ef6c00; border-left: 4px solid #ff9800;',
            error: 'background: #ffebee; color: #c62828; border-left: 4px solid #f44336;'
        };
        return styles[type] || styles.info;
    }
    
    static error(message) {
        this.show(message, 'error');
    }
    
    static success(message) {
        this.show(message, 'success');
    }
    
    static warning(message) {
        this.show(message, 'warning');
    }
}

// モバイル対応 (FR-11)
class MobileController {
    constructor() {
        this.setupViewportHandling();
        this.setupTouchGestures();
    }
    
    setupViewportHandling() {
        // iOS Safariでのviewport-fit対応
        if (this.isIOS()) {
            document.documentElement.style.setProperty(
                '--safe-area-inset-bottom', 
                'env(safe-area-inset-bottom)'
            );
        }
        
        // 仮想キーボード対応
        if ('visualViewport' in window) {
            window.visualViewport.addEventListener('resize', () => {
                this.handleVirtualKeyboard();
            });
        }
        
        // 画面回転対応
        window.addEventListener('orientationchange', () => {
            setTimeout(() => {
                this.adjustLayoutForOrientation();
            }, 500);
        });
    }
    
    handleVirtualKeyboard() {
        const viewport = window.visualViewport;
        const heightDifference = window.innerHeight - viewport.height;
        
        if (heightDifference > 150) { // キーボードが表示された
            document.body.style.setProperty('--keyboard-height', `${heightDifference}px`);
            document.body.classList.add('keyboard-visible');
        } else {
            document.body.style.setProperty('--keyboard-height', '0px');
            document.body.classList.remove('keyboard-visible');
        }
    }
    
    setupTouchGestures() {
        let startY = 0;
        let isScrolling = false;
        
        document.addEventListener('touchstart', (e) => {
            startY = e.touches[0].clientY;
            isScrolling = false;
        }, { passive: true });
        
        document.addEventListener('touchmove', (e) => {
            if (!isScrolling) {
                const currentY = e.touches[0].clientY;
                const diffY = Math.abs(currentY - startY);
                
                if (diffY > 10) {
                    isScrolling = true;
                    autoScrollEnabled = false;
                }
            }
        }, { passive: true });
        
        document.addEventListener('touchend', () => {
            setTimeout(() => {
                const messagesContainer = document.querySelector('.messages-container');
                if (messagesContainer) {
                    const isNearBottom = messagesContainer.scrollTop >= 
                        messagesContainer.scrollHeight - messagesContainer.clientHeight - 100;
                    autoScrollEnabled = isNearBottom;
                }
            }, 100);
        });
    }
    
    isIOS() {
        return /iPad|iPhone|iPod/.test(navigator.userAgent);
    }
    
    adjustLayoutForOrientation() {
        // 画面回転時の調整
        const messagesContainer = document.querySelector('.messages-container');
        if (messagesContainer && autoScrollEnabled) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }
}

// パフォーマンス監視 (FR-15, NFR-01)
class PerformanceMonitor {
    constructor() {
        this.metrics = {
            lcp: 0,
            fid: 0,
            cls: 0,
            interactions: 0,
            errors: 0
        };
        this.setupPerformanceObserver();
    }
    
    setupPerformanceObserver() {
        // Largest Contentful Paint
        if ('PerformanceObserver' in window) {
            new PerformanceObserver((entryList) => {
                const entries = entryList.getEntries();
                const lastEntry = entries[entries.length - 1];
                this.metrics.lcp = lastEntry.startTime;
                this.sendMetrics();
            }).observe({ entryTypes: ['largest-contentful-paint'] });
            
            // First Input Delay
            new PerformanceObserver((entryList) => {
                const entries = entryList.getEntries();
                entries.forEach(entry => {
                    if (entry.processingStart > entry.startTime) {
                        this.metrics.fid = entry.processingStart - entry.startTime;
                        this.sendMetrics();
                    }
                });
            }).observe({ entryTypes: ['first-input'] });
            
            // Cumulative Layout Shift
            let clsValue = 0;
            new PerformanceObserver((entryList) => {
                entries.forEach(entry => {
                    if (!entry.hadRecentInput) {
                        clsValue += entry.value;
                        this.metrics.cls = clsValue;
                    }
                });
            }).observe({ entryTypes: ['layout-shift'] });
        }
    }
    
    recordInteraction(type, duration) {
        this.metrics.interactions++;
        
        window.parent.postMessage({
            type: 'streamlit_performance',
            metric: {
                type: 'interaction',
                interactionType: type,
                duration: duration,
                timestamp: Date.now()
            }
        }, '*');
    }
    
    sendMetrics() {
        window.parent.postMessage({
            type: 'streamlit_performance',
            metrics: this.metrics,
            timestamp: Date.now()
        }, '*');
    }
}

// グローバル関数
window.copyMessage = async function(messageId) {
    const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
    if (messageElement) {
        const text = messageElement.textContent;
        const button = event.target;
        await ClipboardController.copyText(text, button);
    }
};

window.editMessage = function(messageId) {
    window.parent.postMessage({
        type: 'streamlit_edit_message',
        messageId: messageId
    }, '*');
};

window.retryMessage = function(message) {
    window.parent.postMessage({
        type: 'streamlit_retry_message',
        message: message
    }, '*');
};

window.retryStreaming = function(messageId) {
    window.parent.postMessage({
        type: 'streamlit_retry_streaming',
        messageId: messageId
    }, '*');
};

window.sendMessage = function() {
    if (window.inputController) {
        window.inputController.sendMessage();
    }
};

// 初期化
document.addEventListener('DOMContentLoaded', function() {
    // コントローラー初期化
    window.inputController = new InputController();
    window.scrollController = new ScrollController();
    window.streamingController = new StreamingController();
    window.mobileController = new MobileController();
    window.performanceMonitor = new PerformanceMonitor();
    
    // アクセシビリティ設定 (FR-16)
    document.addEventListener('keydown', (e) => {
        // スクリーンリーダー対応
        if (e.altKey && e.key === 's') {
            const messagesContainer = document.querySelector('.messages-container');
            if (messagesContainer) {
                messagesContainer.focus();
            }
        }
    });
    
    console.log('Enhanced chat UI initialized');
});

// エラーハンドリング
window.addEventListener('error', (error) => {
    metrics.errors++;
    console.error('JavaScript error:', error);
    NotificationController.error('エラーが発生しました');
    
    window.parent.postMessage({
        type: 'streamlit_javascript_error',
        error: {
            message: error.message,
            filename: error.filename,
            lineno: error.lineno,
            timestamp: Date.now()
        }
    }, '*');
});

// 未処理のPromise拒否
window.addEventListener('unhandledrejection', (event) => {
    metrics.errors++;
    console.error('Unhandled promise rejection:', event.reason);
    NotificationController.error('処理中にエラーが発生しました');
});
</script>

<style>
/* 通知スタイル */
.notification {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
}

.notification-content {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.notification-close {
    background: none;
    border: none;
    font-size: 18px;
    cursor: pointer;
    padding: 0;
    margin-left: 10px;
    opacity: 0.7;
}

.notification-close:hover {
    opacity: 1;
}

/* キーボード表示時の調整 */
.keyboard-visible .input-container {
    padding-bottom: calc(1rem + var(--keyboard-height, 0px));
}

/* iOS Safari対応 */
@supports (padding: max(0px)) {
    .input-container {
        padding-bottom: max(1rem, calc(1rem + var(--safe-area-inset-bottom, 0px)));
    }
    
    .keyboard-visible .input-container {
        padding-bottom: max(1rem, calc(1rem + var(--safe-area-inset-bottom, 0px) + var(--keyboard-height, 0px)));
    }
}

/* タイピングインディケーター */
.typing-indicator::after {
    content: '●●●';
    animation: typing 1.5s infinite;
    color: #999;
}

@keyframes typing {
    0%, 60%, 100% {
        opacity: 0.4;
    }
    30% {
        opacity: 1;
    }
}

/* アクセシビリティ改善 */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
}

/* ハイコントラストモード */
@media (prefers-contrast: high) {
    .message-bubble-user {
        background: #000;
        color: #fff;
        border: 2px solid #fff;
    }
    
    .message-bubble-bot {
        background: #fff;
        color: #000;
        border: 2px solid #000;
    }
}
</style>
"""
