import requests
import json
import urllib3
import random
import os
from datetime import datetime, timedelta, UTC
from docx import Document
from dotenv import load_dotenv

load_dotenv()
urllib3.disable_warnings()

# =========================================================
# CONFIG
# =========================================================

JIRA_TOKEN = os.getenv("JIRA_TOKEN")
DIFY_API_KEY = os.getenv("DIFY_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

TELEGRAM_CHAT_ID = 6373277315
TARGET_CHAT = -5188678095

JIRA_URL = "https://jira.eltc.ru/rest/api/2/search"
DIFY_URL = "http://localhost/v1/workflows/run"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# =========================================================
# USER MAP (Telegram → Jira)
# =========================================================

USER_MAP = {
    "julia_neverova_dev": {
        "jira_name": "Юлия Неверова",
        "role": "PL/SQL developer, разработчик Борда-бота",
    },
    "shkuratov_i": {
        "jira_name": "Шкуратов Иван",
        "role": "1C developer",
    },
    "shcherbashinn": {
        "jira_name": "Щербашин Никита",
        "role": "Project manager",
    },
    "Sidyakin": {
        "jira_name": "Сидякин Женя",
        "role": "Генеральный директор, заказчик",
    },
}

# =========================================================
# HISTORY
# =========================================================

def load_history():
    if not os.path.exists("messages_history.json"):
        return []

    with open("messages_history.json", "r", encoding="utf-8") as f:
        return json.load(f)


def save_history(messages):
    # храним только последние 500 сообщений
    messages = messages[-500:]

    with open("messages_history.json", "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

# =========================================================
# TELEGRAM OFFSET
# =========================================================

def load_offset():
    if not os.path.exists("telegram_offset.json"):
        return None

    with open("telegram_offset.json", "r") as f:
        return json.load(f).get("offset")


def save_offset(offset):
    with open("telegram_offset.json", "w") as f:
        json.dump({"offset": offset}, f)

# =========================================================
# TELEGRAM FILES
# =========================================================

def download_file(file_id):
    r = requests.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id})
    data = r.json()

    file_path = data["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

    file_data = requests.get(file_url).content
    path = "protocol.docx"

    with open(path, "wb") as f:
        f.write(file_data)

    return path


def read_docx(path):
    doc = Document(path)
    text = []

    for p in doc.paragraphs:
        if p.text.strip():
            text.append(p.text)

    return "\n".join(text)

# =========================================================
# PROTOCOL SUMMARY
# =========================================================

def summarize_protocol(text):
    payload = {
        "inputs": {"protocol_text": text},
        "query": "summarize meeting protocol",
        "response_mode": "blocking",
        "user": "argus",
    }

    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }

    r = requests.post(DIFY_URL, headers=headers, json=payload, timeout=60)

    result = r.json()
    data = result.get("data", {})
    outputs = data.get("outputs", {})

    summary = outputs.get("result")

    if not summary:
        return ""

    return summary.replace("```", "").strip()

# =========================================================
# TELEGRAM SEND
# =========================================================

def send_telegram(text):
    url = f"{TELEGRAM_API}/sendMessage"

    payload = {
        #"chat_id": TARGET_CHAT,
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        requests.post(
            url,
            json=payload,
            timeout=10,
            verify=False,
            proxies={"http": None, "https": None},
        )
    except Exception as e:
        print("Telegram send error:", e)

# =========================================================
# JIRA
# =========================================================

def load_jira():

    params = {
        "jql": '("Epic Link" = ITS-16120 OR parent = ITS-16120) AND statusCategory != Done',
        "maxResults": 50,
        "startAt": 0,
        "fields": "summary,status,assignee,updated,timetracking,parent,comment",
    }

    headers = {
        "Authorization": f"Bearer {JIRA_TOKEN}",
        "Accept": "application/json",
    }

    r = requests.get(
        JIRA_URL,
        headers=headers,
        params=params,
        timeout=30,
        proxies={"http": None, "https": None},
    )

    data = r.json()

    if "issues" not in data:
        print("Jira API error:")
        print(data)
        return []

    issues = []

    for issue in data["issues"]:
        fields = issue["fields"]
        parent = fields["parent"]["key"] if fields.get("parent") else None

        # --- comments ---
        comments_data = fields.get("comment", {}).get("comments", [])
        comments = []

        for c in comments_data:
            comments.append(
                {
                    "author": c.get("author", {}).get("displayName", "unknown"),
                    "text": c.get("body", ""),
                    "time": c.get("created"),
                }
            )

        # --- time tracking ---
        timetracking = fields.get("timetracking", {})
        spent_hours = round(timetracking.get("timeSpentSeconds", 0) / 3600, 1)
        remaining_hours = round(
            timetracking.get("remainingEstimateSeconds", 0) / 3600, 1
        )

        assignee = (
            fields["assignee"]["displayName"]
            if fields.get("assignee")
            else "не назначен"
        )

        status = fields["status"]["name"]

        if status in ["Open"]:
            continue

        issues.append(
            {
                "key": issue["key"],
                "summary": fields["summary"],
                "status": status,
                "assignee": assignee,
                "updated": fields["updated"],
                "spent": spent_hours,
                "remaining": remaining_hours,
                "parent": parent,
                "comments": comments,
            }
        )

    print("Total issues in Jira:", data.get("total"))
    return issues

# =========================================================
# GROUP ISSUES
# =========================================================

def group_issues(issues):
    grouped = {}
    subtasks = []

    for issue in issues:
        if issue["parent"]:
            subtasks.append(issue)
        else:
            grouped[issue["key"]] = {"task": issue, "subtasks": []}

    for sub in subtasks:
        parent = sub["parent"]

        if parent in grouped:
            grouped[parent]["subtasks"].append(sub)
        else:
            grouped[sub["key"]] = {"task": sub, "subtasks": []}

    return grouped

# =========================================================
# TELEGRAM UTIL
# =========================================================

def message_exists(history, msg):
    for h in history:
        if h["time"] == msg["time"] and h["text"] == msg["text"]:
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

def load_telegram():

    history = load_history()
    offset = load_offset()

    params = {}
    if offset:
        params["offset"] = offset

    r = requests.get(
        f"{TELEGRAM_API}/getUpdates",
        params=params,
        timeout=20,
        verify=False,
        proxies={"http": None, "https": None},
    )

    data = r.json()

    new_messages = []
    cutoff = get_time_window()
    max_update_id = None

    for upd in data["result"]:

        update_id = upd["update_id"]

        if not max_update_id or update_id > max_update_id:
            max_update_id = update_id

        msg = upd.get("message")
        if not msg:
            continue

        chat_id = msg["chat"]["id"]
        if chat_id != TARGET_CHAT:
            continue

        text = msg.get("text")
        if not text:
            continue

        msg_time = datetime.fromtimestamp(msg["date"], UTC)

        if msg_time < cutoff:
            continue

        user = msg.get("from", {}).get("username", "unknown")
        user_info = USER_MAP.get(user)

        jira_user = user_info["jira_name"] if user_info else "unknown"
        role = user_info["role"] if user_info else "unknown"

        msg_obj = {
            "telegram_user": user,
            "jira_user": jira_user,
            "role": role,
            "text": text,
            "time": msg_time.isoformat(),
        }

        if not message_exists(history, msg_obj):
            new_messages.append(msg_obj)
            history.append(msg_obj)

    save_history(history)

    print("New messages:", len(new_messages))

    if max_update_id:
        save_offset(max_update_id + 1)

    return history

# =========================================================
# FIND ISSUE CANDIDATES
# =========================================================

def find_candidates(issues, messages, max_candidates=5):

    text = " ".join(m["text"].lower() for m in messages)

    scored = []

    for issue in issues:

        summary = issue["summary"].lower()
        score = 0

        for word in summary.split():
            if len(word) < 5:
                continue
            if word in text:
                score += 1

        if score > 0:
            scored.append((score, issue))

    scored.sort(reverse=True, key=lambda x: x[0])

    if not scored:
        return issues[:max_candidates]

    return [s[1] for s in scored[:max_candidates]]

# =========================================================
# CONTEXT BUILDER
# =========================================================

def build_context(issues, messages, candidates):

    grouped = group_issues(issues)

    candidate_text = "Задачи-кандидаты (возможно обсуждаются):\n\n"

    for c in candidates:
        candidate_text += f"{c['key']} — {c['summary']}\n"

    candidate_text += "\n"

    jira_text = "Активные задачи проекта:\n\n"

    for g in grouped.values():

        i = g["task"]

        jira_text += (
            f"Задача: {i['key']}\n"
            f"Название: {i['summary']}\n"
            f"Статус: {i['status']}\n"
            f"Исполнитель: {i['assignee']}\n"
            f"Залогировано часов: {i['spent']}\n"
            f"Осталось часов: {i['remaining']}\n"
            f"Последний апдейт: {i['updated']}\n"
        )

        if i["parent"]:
            jira_text += f"Родительская задача: {i['parent']}\n"

        if g["subtasks"]:

            jira_text += "Подзадачи:\n"

            for sub in g["subtasks"]:
                jira_text += (
                    f"  - {sub['key']} — {sub['summary']} "
                    f"(статус: {sub['status']}, исполнитель: {sub['assignee']})\n"
                )

        jira_text += "Комментарии:\n"

        for c in i.get("comments", [])[:5]:
            jira_text += f"  - {c['author']} ({c['time']}): {c['text']}\n"

        jira_text += "\n"

    tg_text = "Обсуждение команды:\n\n"

    for m in messages:
        tg_text += (
            f"{m['jira_user']} (telegram: {m['telegram_user']}, "
            f"role: {m['role']}) : {m['text']}\n"
        )

    return candidate_text + jira_text, tg_text

# =========================================================
# ARGUS QUOTES
# =========================================================

def load_quotes():
    try:
        with open("argus_quotes.txt", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print("Ошибка загрузки цитат:", e)
        return ["Argus сегодня без цитаты, но с настроением."]


def load_quote_history():
    try:
        with open("argus_quotes_history.json", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_quote_history(history):
    with open("argus_quotes_history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def argus_quote():

    quotes = load_quotes()
    history = load_quote_history()

    now = datetime.now()

    # оставляем только цитаты за последние 7 дней
    week_ago = now - timedelta(days=7)

    history = [
        h for h in history
        if datetime.fromisoformat(h["time"]) > week_ago
    ]

    used_quotes = [h["quote"] for h in history]

    available_quotes = [q for q in quotes if q not in used_quotes]

    # если все цитаты использованы — начинаем заново
    if not available_quotes:
        available_quotes = quotes

    quote = random.choice(available_quotes)

    history.append({
        "quote": quote,
        "time": now.isoformat()
    })

    save_quote_history(history)

    return quote
    
# =========================================================
# DIFY ANALYSIS
# =========================================================

def risk_icon(value):
    if value >= 70:
        return "🔴"
    if value >= 40:
        return "🟠"
    return "🟢"


def analyze(jira_context, tg_context, issues):

    payload = {
        "inputs": {
            "jira_context": jira_context,
            "tg_context": tg_context
        },
        "query": "project risk analysis",
        "response_mode": "blocking",
        "user": "argus"
    }

    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }

    r = requests.post(
        DIFY_URL,
        headers=headers,
        json=payload,
        timeout=1000
    )

    result = r.json()

    data = result.get("data", {})
    outputs = data.get("outputs", {})

    raw = outputs.get("result")

    if not raw:
        print("Нет результата от модели")
        print(result)
        return

    # убираем markdown ```json
    raw = raw.replace("```json", "").replace("```", "").strip()

    analysis = json.loads(raw)

    print("\n=== AI PROJECT ANALYSIS ===\n")

    icon = risk_icon(analysis["project_risk"])

    report = "🤖 <b>ARGUS — утренний анализ проекта</b>\n\n"
    report += "☀️ Доброе утро, команда!\n\n"
    report += f"📊 <b>Общий риск проекта:</b> {icon} {analysis['project_risk']}%\n\n"

    print(f"Общий риск проекта: {icon} {analysis['project_risk']}%\n")
    print("Риски по задачам:\n")

    report += "🎯 <b>Риски по задачам:</b>\n\n"

    for issue in analysis["issues"]:

        icon = risk_icon(issue["risk"])

        summary = next(
            (i["summary"] for i in issues if i["key"] == issue["key"]),
            "Название неизвестно"
        )

        print(f"{icon} {issue['key']} — {issue['risk']}%")
        print(f"   задача: {summary}")
        print(f"   причина: {issue['reason']}\n")

        report += f"{issue['key']} — {issue['risk']}%\n"
        report += f"{summary}\n"
        report += f"{issue['reason']}\n\n"

    print("Общий вывод:\n")

    summary = analysis.get("summary")

    if not summary:

        high_risk = [
            i for i in analysis["issues"]
            if i["risk"] >= 40
        ]

        if high_risk:
            summary = "Обнаружены потенциальные риски по задачам: "
            summary += ", ".join(i["key"] for i in high_risk)
        else:
            summary = "Критических рисков не обнаружено."

    print(summary)

    report += "🚀 <b>Итог:</b>\n\n"
    report += summary

    quote = argus_quote()

    report += "\n\n────────────────────\n\n"
    report += "💬 <b>Цитата дня от Argus</b>\n\n"
    report += f"{quote}"

    send_telegram(report)
    
# --------------------------------
# MAIN
# --------------------------------

print("Loading Jira...")

issues = load_jira()

print("Loaded issues:", len(issues))

print("Loading Telegram...")

messages = load_telegram()

print("Loaded messages:", len(messages))

candidates = find_candidates(issues, messages)
print("\nCandidate issues:")

for c in candidates:
    print(c["key"], "-", c["summary"])
    
jira_context, tg_context = build_context(issues, messages, candidates)

print("\nSending to Dify...\n")

analyze(jira_context, tg_context, issues)
