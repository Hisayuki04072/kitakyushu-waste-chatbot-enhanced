import os, time, json, requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://160.251.239.159:8080/api")

CHAT_BLOCK = f"{BACKEND_URL}/chat/blocking"
CHAT_STREAM = f"{BACKEND_URL}/chat/streaming"
UPLOAD_API = f"{BACKEND_URL}/upload"
GPU_API = f"{BACKEND_URL}/monitor/gpu"
HEALTH_API = f"{BACKEND_URL}/health"

st.set_page_config(page_title="北九州市ごみ分別チャットボット", page_icon="♻️", layout="wide")
st.title("♻️ 北九州市ごみ分別チャットボット（RAG + Ollama）")

# 侧栏：健康检查 & GPU
with st.sidebar:
    st.header("サーバーステータス")
    try:
        r = requests.get(HEALTH_API, timeout=5)
        if r.status_code == 200:
            st.success("API: Healthy")
        else:
            st.warning("API: Unhealthy")
        if isinstance(r.json(), dict) and "details" in r.json():
            st.json(r.json()["details"])
    except Exception as e:
        st.error(f"Health error: {e}")

    st.divider()
    st.header("GPU モニタ")
    try:
        g = requests.get(GPU_API, timeout=5).json()
        if g.get("ok"):
            used = g.get("memory_used_mb", 0)
            total = g.get("memory_total_mb", 1)
            st.metric("VRAM 使用量", f"{used} / {total} MB")
            st.metric("利用率", f"{g.get('utilization_percent', 0)}%")
        else:
            st.warning(g.get("error", "取得失敗"))
    except Exception as e:
        st.error(f"GPU error: {e}")

# 会话状态
if "history" not in st.session_state:
    st.session_state.history = []

# 阻塞式调用
def chat_blocking(prompt: str):
    r = requests.post(CHAT_BLOCK, json={"prompt": prompt}, timeout=120)
    r.raise_for_status()
    return r.json()

# 流式调用
def chat_streaming(prompt: str, placeholder):
    with requests.post(
        CHAT_STREAM, json={"prompt": prompt}, stream=True, timeout=300,
        headers={"Accept": "text/event-stream"}
    ) as resp:
        resp.raise_for_status()
        full = ""
        for line in resp.iter_lines(decode_unicode=True):
            if not line: 
                continue
            if line.startswith("data: "):
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                    if obj.get("type") == "chunk":
                        full += obj.get("content", "")
                        placeholder.markdown(full + "▌")
                except Exception:
                    pass
        return {"response": full}

# 页面：聊天
st.subheader("💬 ごみ分別質問")
mode = st.radio("回答モード", ["blocking", "streaming"], horizontal=True)
q = st.text_input("質問（例：アルミ缶はどう捨てますか？）")

if st.button("送信", type="primary") and q.strip():
    t0 = time.time()
    try:
        if mode == "blocking":
            data = chat_blocking(q)
            ans = data.get("response", "")
        else:
            area = st.empty()
            data = chat_streaming(q, area)
            ans = data.get("response", "")
        st.session_state.history.append({"role": "user", "text": q})
        st.session_state.history.append({"role": "assistant", "text": ans, "latency": time.time()-t0})
    except Exception as e:
        st.error(f"エラー: {e}")

# 历史
if st.session_state.history:
    st.subheader("📝 質問履歴")
    for m in st.session_state.history[-10:]:
        if m["role"] == "user":
            st.chat_message("user").write(m["text"])
        else:
            st.chat_message("assistant").write(m["text"])
            if "latency" in m:
                st.caption(f"⏱ {m['latency']:.2f}s")

# 上传
st.subheader("📤 CSV アップロード（ナレッジ登録）")
up = st.file_uploader("CSV ファイル", type=["csv"])
if up and st.button("アップロード"):
    try:
        files = {"file": (up.name, up.getvalue(), "text/csv")}
        r = requests.post(UPLOAD_API, files=files, timeout=120)
        r.raise_for_status()
        st.success(f"アップロード成功: {r.json()}")
    except Exception as e:
        st.error(f"アップロード失敗: {e}")
