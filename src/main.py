import socket
import time

def wait_for_vpn(host="jira.eltc.ru", port=443):
    print("⏳ Waiting for VPN connection...")

    while True:
        try:
            socket.create_connection((host, port), timeout=5)
            print("✅ VPN connection established")
            return
        except OSError:
            print("❌ No VPN yet, retry in 30 sec...")
            time.sleep(30)
            
from src.utils.projects import load_projects
from src.collectors.jira import load_jira
from src.collectors.telegram import load_telegram
from src.collectors.pdf import (
    is_pdf_processed,
    download_file,
    extract_summary_from_pdf,
    add_summary,
    mark_pdf_processed,
)
from src.analyzers.risk_analyzer import (
    find_candidates,
    build_context,
    analyze,
    is_monday,
    calculate_status_distribution,
)

wait_for_vpn()

projects = load_projects()

for project_key, project in projects.items():

    print(f"\n=== {project['name']} ({project_key}) ===\n")

    # --- JIRA ---
    print("Loading Jira (active)...")
    issues_active = load_jira(project["jql"])
    print("Loaded active issues:", len(issues_active))

    print("Loading Jira (all)...")
    issues_all = load_jira(project.get("jql_all", project["jql"]))
    print("Loaded all issues:", len(issues_all))

    # --- TELEGRAM ---
    print("Loading Telegram...")
    messages = load_telegram(project)
    print("Loaded messages:", len(messages))
    
    # --- PDF PROCESSING ---
    for msg in messages:

        protocol_bot = project.get("protocol_bot")
        is_protocol = (
            msg.get("forward_from") == protocol_bot
        )

        has_pdf = (msg.get("file_name") or "").lower().endswith(".pdf")

        if (
            msg.get("file_id")
            and (msg.get("file_name") or "").lower().endswith(".pdf")
            and msg.get("file_id") and has_pdf and is_protocol
        ):

            if is_pdf_processed(msg["file_id"], project):
                continue

            print("Found PDF:", msg["file_name"])

            path = download_file(msg["file_id"], project)

            if not path:
                continue

            summary = extract_summary_from_pdf(path)

            if summary:
                add_summary(summary, project)

            mark_pdf_processed(msg["file_id"], project)

    # Ограничиваем данные
    messages = messages[-80:]
    issues_for_analysis = issues_active[:10]

    # --- CANDIDATES ---
    candidates = find_candidates(issues_active, messages)
    candidates = candidates[:5]

    print("\nCandidate issues:")
    for c in candidates:
        print(c["key"], "-", c["summary"])

    # --- CONTEXT ---
    jira_context, tg_context = build_context(issues_active, messages, candidates, project)

    # --- ANALYZE ---
    print("\nSending to Dify...\n")

    # передаём active задачи для анализа    
    for attempt in range(3):

        print(f"\nSending to Dify (attempt {attempt+1})...\n")

        success = analyze(
            jira_context,
            tg_context,
            issues_for_analysis,
            issues_all,
            project
        )

        if success:
            break

        # 🔻 уменьшаем контекст
        messages = messages[-50:]
        issues_for_analysis = issues_for_analysis[:7]

        jira_context, tg_context = build_context(
            issues_for_analysis,
            messages,
            candidates,
            project
        )

    # --- WEEKLY METRICS (опционально) ---
    if is_monday():
        stats = calculate_status_distribution(issues_all)
        print("\nWeekly status distribution:")
        for k, v in stats.items():
            print(f"{k}: {v}%")
