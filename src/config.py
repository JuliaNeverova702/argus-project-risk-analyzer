import os
from dotenv import load_dotenv

load_dotenv()

JIRA_TOKEN = os.getenv("JIRA_TOKEN")
DIFY_API_KEY = os.getenv("DIFY_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

CONFLUENCE_USER = os.getenv("CONFLUENCE_USER")
CONFLUENCE_PASSWORD = os.getenv("CONFLUENCE_PASSWORD")

JIRA_URL = ""
DIFY_URL = ""
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
