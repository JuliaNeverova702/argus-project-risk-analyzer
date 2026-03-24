import requests
import urllib3
urllib3.disable_warnings()

from src.config import *

def load_jira(jql):

    params = {
        "jql": jql,
        "maxResults": 50,
        "startAt": 0,
        "fields": "summary,status,assignee,updated,timetracking,parent,comment,description"
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
        proxies={"http": None, "https": None}
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
        
        if status.lower() in ["done", "closed", "resolved", "закрыто", "выполнено"]:
            continue
            
        summary = fields["summary"]

        if status in ["Open"]:
            continue

        # 🔥 фильтр дейли
        if "дейли" in summary.lower():
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
                "description": fields.get("description", "")
            }
        )

    print("Total issues in Jira:", data.get("total"))
    return issues