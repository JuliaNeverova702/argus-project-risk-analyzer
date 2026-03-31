import requests
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime

from src.config import CONFLUENCE_USER, CONFLUENCE_PASSWORD

def clean_confluence_html(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    return " ".join(text.split())[:3000]


def load_confluence(project):

    page_ids = project.get("confluence_pages")

    if not page_ids:
        return ""

    texts = []

    for page_id in page_ids:
        try:
            url = f"https://confluence.ru/rest/api/content/{page_id}" # use your confluence's url

            r = requests.get(
                url,
                auth=HTTPBasicAuth(CONFLUENCE_USER, CONFLUENCE_PASSWORD),
                params={"expand": "body.storage"},
                timeout=30,
                proxies={"http": None, "https": None}
            )

            data = r.json()

            html = data["body"]["storage"]["value"]
            text = clean_confluence_html(html)

            texts.append(text)

        except Exception as e:
            print(f"Confluence error ({page_id}):", e)

    return "\n\n".join(texts)
    
def load_conf_summary(project):
    filename = f"confluence_summary_{project['name']}.json"

    if not os.path.exists(filename):
        return None

    with open(filename, encoding="utf-8") as f:
        return json.load(f)


def save_conf_summary(summary, project):
    filename = f"confluence_summary_{project['name']}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump({
            "text": summary,
            "updated": datetime.now().isoformat()
        }, f, ensure_ascii=False, indent=2)
        
def get_confluence_summary(project):

    saved = load_conf_summary(project)

    if saved:
        return saved["text"]

    print("Generating Confluence summary via Dify...")

    raw_text = load_confluence(project)

    if not raw_text:
        return ""

    raw_text = raw_text[:3000]

    summary = summarize_confluence(raw_text)

    save_conf_summary(summary, project)

    return summary

def summarize_confluence(text):

    payload = {
        "inputs": {
            "text": text
        },
        "query": "summarize confluence",
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
            timeout=300
        )

        result = r.json()

        data = result.get("data", {})
        outputs = data.get("outputs", {})

        summary = outputs.get("result")

        if not summary:
            print("Dify summary empty")
            return text[:2000]

        return summary.strip()

    except Exception as e:
        print("Dify summary error:", e)
        return text[:1500]
