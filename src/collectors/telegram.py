import requests
import json
import os
from datetime import datetime, timedelta, UTC
import urllib3
urllib3.disable_warnings()

from src.config import *

# =========================================================
# DOWNLOAD FILE
# =========================================================

def download_file(file_id, project):

    # 1. получаем путь
    url = f"{TELEGRAM_API}/getFile"

    r = requests.get(url, params={"file_id": file_id})
    data = r.json()

    if "result" not in data:
        print("Ошибка Telegram getFile:")
        print(data)
        return None

    file_path = data["result"]["file_path"]

    # 2. скачиваем файл
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

    local_path = f"files/{project['name']}_{file_id}.pdf"

    os.makedirs("files", exist_ok=True)

    r = requests.get(download_url)

    with open(local_path, "wb") as f:
        f.write(r.content)

    return local_path
    
# =========================================================
# HISTORY
# =========================================================

def load_history(project):

    filename = f"messages_history_{project['name']}.json"

    if not os.path.exists(filename):
        return []

    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def save_history(messages, project):

    messages = messages[-500:]

    filename = f"messages_history_{project['name']}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

# =========================================================
# TELEGRAM OFFSET
# =========================================================

def load_offset(project):

    filename = "telegram_offset.json"

    if not os.path.exists(filename):
        return None

    with open(filename, "r") as f:
        return json.load(f).get("offset")


def save_offset(offset, project):

    filename = "telegram_offset.json"

    with open(filename, "w") as f:
        json.dump({"offset": offset}, f)

# =========================================================
# TELEGRAM SEND
# =========================================================

def send_telegram(text, project):
    url = f"{TELEGRAM_API}/sendMessage"

    payload = {
        "chat_id": project["chat_id"],
        "text": text,
        "parse_mode": "HTML",
    }

    for attempt in range(3):
        try:
            requests.post(
                url,
                json=payload,
                timeout=30
            )
            break
        except Exception as e:
            print(f"Telegram send error (attempt {attempt+1}):", e)
            
            
# =========================================================
# TELEGRAM UTIL
# =========================================================

def message_exists(history, msg):
    for h in history:
        if h["time"] == msg["time"] and h.get("text") == msg.get("text"):
            return True
    return False


def get_time_window():
    now = datetime.now(UTC)

    # Monday = 0
    hours = 72 if now.weekday() == 0 else 24

    return now - timedelta(hours=hours)

# =========================================================
# TELEGRAM LOAD
# =========================================================

def load_telegram(project):
    
    user_map = project.get("user_map", {})
    history = load_history(project)
    params = {}

    try:
        r = requests.get(
            f"{TELEGRAM_API}/getUpdates",
            params=params,
            timeout=20,
            #verify=False,
            proxies={"http": None, "https": None}
        )
    except requests.exceptions.SSLError as e:
        print("SSL ошибка Telegram:", e)
        return history

    except requests.exceptions.RequestException as e:
        print("Ошибка сети Telegram:", e)
        return history

    data = r.json()

    new_messages = []
    cutoff = get_time_window()
    max_update_id = None
    
    if not data.get("ok"):
        print("Telegram API error:", data)
        return history

    for upd in data.get("result", []):

        update_id = upd["update_id"]

        if not max_update_id or update_id > max_update_id:
            max_update_id = update_id

        msg = upd.get("message")
        if not msg:
            continue
        
        forward_from = msg.get("forward_from", {})
        forward_origin = msg.get("forward_origin", {})

        forward_username = None

        # новый формат
        if forward_origin.get("type") == "user":
            forward_username = forward_origin.get("sender_user", {}).get("username")

        # старый формат
        if not forward_username:
            forward_username = forward_from.get("username")
        
        chat_id = msg.get("chat", {}).get("id")
        if chat_id != project["chat_id"]:
            continue

        text = (msg.get("text") or "").replace("\n", " ").strip()

        document = msg.get("document")

        file_id = None
        file_name = None

        if document:
            file_id = document.get("file_id")
            file_name = document.get("file_name")

        msg_time = datetime.fromtimestamp(msg["date"], UTC)

        if msg_time < cutoff:
            continue

        user = msg.get("from", {}).get("username", "unknown")
        user_info = user_map.get(user, {})
        
        jira_user = user_info["jira_name"] if user_info else "unknown"
        role = user_info["role"] if user_info else "unknown"

        msg_obj = {
            "telegram_user": user,
            "jira_user": jira_user,
            "role": role,
            "text": text,
            "time": msg_time.isoformat(),
            "file_id": file_id,
            "file_name": file_name,
            "forward_from": forward_username
        }

        if not message_exists(history, msg_obj):
            new_messages.append(msg_obj)
            history.append(msg_obj)
    
    save_history(history, project)

    print("New messages:", len(new_messages))

    return history