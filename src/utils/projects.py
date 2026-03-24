import json
from pathlib import Path

def load_projects():
    path = Path(__file__).resolve().parent.parent.parent / "config" / "projects.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)