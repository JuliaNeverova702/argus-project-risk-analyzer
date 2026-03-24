import json
from datetime import datetime, UTC

from src.utils.quotes import argus_quote
from src.collectors.confluence import get_confluence_summary
from src.collectors.pdf import load_summaries
from src.collectors.telegram import send_telegram

# =========================================================
# EVALUATE ISSUES
# =========================================================
def evaluate_issues(issues):

    now = datetime.now(UTC)
    results = []

    for i in issues:

        flags = []

        updated = datetime.fromisoformat(i["updated"].replace("Z", "+00:00"))
        hours_since_update = (now - updated).total_seconds() / 3600

        # 🔥 1. Нет активности
        if hours_since_update > 30:
            flags.append("нет активности >30ч")

        # 🔥 2. Нет комментариев
        if not i["comments"] and hours_since_update > 30:
            flags.append("нет комментариев >30ч")

        # 🔥 3. Долго висит
        if i["spent"] > 40:
            flags.append("задача >40ч")

        elif i["spent"] > 30:
            flags.append("задача >30ч")

        # 🔥 4. перерасход
        if i["spent"] > 0 and i["remaining"] >= 0:
            total = i["spent"] + i["remaining"]
            if total > 0:
                progress = i["spent"] / total
                if progress > 0.7 and i["remaining"] > 0:
                    flags.append("перерасход времени")

        # 🔥 5. планирование
        if i["status"].lower() in ["planning", "планирование"]:
            if i["spent"] > 4:
                flags.append("много часов на планирование")

        # 🔥 6. backlog
        if i["status"].lower() == "backlog" and i["spent"] > 0:
            flags.append("часы в backlog")

        if flags:
            results.append({
                "key": i["key"],
                "summary": i["summary"],
                "flags": flags
            })

    return results

# =========================================================
# CALCULATE ISSUE STATUSES
# =========================================================
def calculate_status_distribution(issues):

    total = len(issues)

    if total == 0:
        return {}

    stats = {}

    for issue in issues:
        status = issue["status"]
        stats[status] = stats.get(status, 0) + 1

    # переводим в проценты
    percent_stats = {
        status: round((count / total) * 100)
        for status, count in stats.items()
    }

    return percent_stats
    
def format_status_distribution(stats):

    if not stats:
        return "Нет данных"

    text = "📊 <b>Распределение задач по статусам:</b>\n\n"

    for status, percent in sorted(stats.items(), key=lambda x: -x[1]):
        text += f"• {status}: {percent}%\n"

    return text
    
def is_monday():
    return datetime.now().weekday() == 0
    
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
# FIND ISSUE CANDIDATES
# =========================================================

def find_candidates(issues, messages, max_candidates=5):

    text = " ".join((m.get("text") or "").lower() for m in messages)

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

def compress_issues_for_context(issues):
    result = []

    for i in issues[:10]:  # не больше 10 задач
        text = (
            f"{i['key']} | {i['status']} | {i['assignee']} | "
            f"spent={i['spent']}h remaining={i['remaining']}h | "
            f"updated={i['updated']}"
        )

        if i.get("description"):
            text += f" | desc: {i['description'][:200]}"

        result.append(text)

    return "\n".join(result)
    
# =========================================================
# CONTEXT BUILDER
# =========================================================

def build_context(issues, messages, candidates, project):
    
    conf_text = get_confluence_summary(project)

    if conf_text:
        conf_text = conf_text[:1000]  # 🔥 ключевой момент
        conf_text = "Документация проекта:\n\n" + conf_text + "\n\n"
    else:
        conf_text = ""
        
    flags = evaluate_issues(issues)

    flags_text = "Системные сигналы по задачам:\n\n"

    for f in flags[:10]:
        flags_text += f"{f['key']} — {', '.join(f['flags'])}\n"

    flags_text += "\n\n"
    
    summaries = load_summaries(project)

    summary_text = "Сводка дейли (последние дни):\n\n"

    for s in summaries[-5:]:
        summary_text += s["text"] + "\n\n---\n\n"
        
    grouped = group_issues(issues)

    candidate_text = "Задачи-кандидаты (возможно обсуждаются):\n\n"

    for c in candidates:
        candidate_text += f"{c['key']} — {c['summary']}\n"

    candidate_text += "\n"

    jira_text = "Активные задачи проекта (сжато):\n\n"
    jira_text += compress_issues_for_context(issues)

    tg_text = "Обсуждение команды:\n\n"

    for m in messages:
        tg_text += (
            f"{m['jira_user']} (telegram: {m['telegram_user']}, "
            f"role: {m['role']}) : {m['text']}\n"
        )

    return conf_text + summary_text + flags_text + candidate_text + jira_text, tg_text
    
def group_insights(insights):
    grouped = {}

    for s in insights:
        key = s["insight"]

        if key not in grouped:
            grouped[key] = []

        grouped[key].append(s["key"])

    return grouped


def classify_risk(reason: str):
    r = reason.lower()

    if "нет активности" in r and "нет комментариев" in r:
        return "Нет активности и коммуникации по задаче"

    if "нет активности" in r:
        return "Нет активности по задаче"

    if "нет комментариев" in r:
        return "Нет коммуникации по задаче"

    if "перерасход" in r:
        return "Перерасход времени"

    if "задача >" in r:
        return "Задача выполняется слишком долго"

    # 🔥 вот это главное изменение
    if "завис" in r or "зависим" in r:
        return "Задача зависит от других задач или заблокирована"

    if "блок" in r:
        return "Задача заблокирована"

    if "недоработ" in r:
        return "Требуется доработка задачи"

    return "Прочие проблемы"
    
def group_issues_by_reason(issues):
    grouped = {}

    for i in issues:
        key = classify_risk(i["reason"])

        if key not in grouped:
            grouped[key] = []

        grouped[key].append(i)

    return grouped
    
# =========================================================
# DIFY ANALYSIS
# =========================================================

def risk_icon(value):
    if value >= 70:
        return "🔴"
    if value >= 40:
        return "🟠"
    return "🟢"

def analyze(jira_context, tg_context, issues_active, issues_all, project):
    
    issue_flags = evaluate_issues(issues_active)
    
    payload = {
        "inputs": {
            "jira_context": jira_context,
            "tg_context": tg_context,
            "issue_flags": json.dumps(issue_flags, ensure_ascii=False)
        },
        "query": "project risk analysis",
        "response_mode": "blocking",
        "user": "argus"
    }

    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        r = requests.post(
            DIFY_URL,
            headers=headers,
            json=payload,
            timeout=120
        )

        result = r.json()

    except Exception as e:
        print("Dify request error:", e)
        return False
    
    data = result.get("data", {})
    outputs = data.get("outputs", {})

    raw = outputs.get("result")

    if not raw:
        print("Нет результата от модели")

        return False

    # убираем markdown ```json
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        analysis = json.loads(raw)
        valid_keys = {i["key"] for i in issues_active}

        analysis["issues"] = [
            i for i in analysis.get("issues", [])
            if i["key"] in valid_keys
        ]

        analysis["system_insights"] = [
            i for i in analysis.get("system_insights", [])
            if i["key"] in valid_keys
        ]
    except Exception:
        print("JSON parse error:", raw)
        return

    icon = risk_icon(analysis["project_risk"])
    if issue_flags:
        analysis["project_risk"] = max(analysis["project_risk"], 40)

    report = "🤖 <b>ARGUS — утренний анализ проекта</b>\n\n"
    report += "☀️ Доброе утро, команда!\n\n"
    report += f"📊 <b>Общий риск проекта:</b> {icon} {analysis['project_risk']}%\n\n"

    report += "🎯 <b>Риски по задачам:</b>\n\n"

    issue_keys = {i["key"] for i in analysis["issues"]}

    system_insights = [
        s for s in analysis.get("system_insights", [])
        if s["key"] not in issue_keys
    ]

    grouped_issues = group_issues_by_reason(analysis["issues"])

    for reason, items in grouped_issues.items():

        if len(items) == 1:
            issue = items[0]

            jira_url = f"https://jira.eltc.ru/browse/{issue['key']}"

            summary = next(
                (i["summary"] for i in issues_active if i["key"] == issue["key"]),
                "Название неизвестно"
            )

            report += f"🔗 <a href='{jira_url}'><b>{issue['key']}</b></a> — {issue['risk']}%\n"
            report += f"{summary}\n"
            report += f"{reason}\n\n"

        else:
            keys = [i["key"] for i in items]

            keys_str = ", ".join(
                f"<a href='https://jira.eltc.ru/browse/{k}'>{k}</a>"
                for k in keys[:5]
            )

            report += f"🔗 {len(items)} задач(-и) — {reason}:\n{keys_str}\n\n"

    if system_insights:
        report += "\n\n🧠 <b>Системные наблюдения</b>\n\n"

        grouped = group_insights(system_insights)

        for insight, keys in list(grouped.items())[:5]:
            
            if len(keys) == 1:
                jira_url = f"https://jira.eltc.ru/browse/{keys[0]}"
                report += f"🔎 <a href='{jira_url}'>{keys[0]}</a> — {insight}\n"
            else:
                keys_str = ", ".join(
                    f"<a href='https://jira.eltc.ru/browse/{k}'>{k}</a>"
                    for k in keys[:5]
                )
                report += f"🔎 {len(keys)} задач — {insight}:\n{keys_str}\n\n"
    else:
        report += "\n"
        
    summary = analysis.get("summary", "")

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

    report += "🚀 <b>Итог:</b>\n\n"
    report += summary
    
    manager_advice = analysis.get("manager_advice", [])
    
    if is_monday():
        stats = calculate_status_distribution(issues_all)
        report += "\n\n" + format_status_distribution(stats)
    
    if manager_advice:
        report += "\n\n🧭 <b>Рекомендации менеджеру</b>\n\n"
        for advice in manager_advice[:5]:
            report += f"• {advice}\n"
        
    quote = argus_quote(project)

    report += "\n────────────────────\n\n"
    report += "💬 <b>Цитата дня от Argus</b>\n\n"
    report += f"{quote}"

    send_telegram(report, project)
    return True