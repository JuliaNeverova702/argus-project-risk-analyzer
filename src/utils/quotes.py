import json
import random
from datetime import datetime, timedelta

def load_quotes():
    try:
        with open("argus_quotes.txt", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print("Ошибка загрузки цитат:", e)
        return ["Argus сегодня без цитаты, но с настроением."]


def load_quote_history(project):

    filename = f"argus_quotes_history_{project['name']}.json"

    try:
        with open(filename, encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_quote_history(history, project):

    filename = f"argus_quotes_history_{project['name']}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def argus_quote(project):

    quotes = load_quotes()
    history = load_quote_history(project)

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

    save_quote_history(history, project)

    return quote