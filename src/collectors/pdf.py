import json
import os
from datetime import datetime
import pdfplumber

def extract_summary_from_pdf(file_path):
    text = ""

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages[:3]:  # первые страницы
            page_text = page.extract_text()
            if page_text:
                text += page_text + " "

    start = text.find("Супер краткое содержание")
    end = text.find("Саммари по темам")

    if start == -1:
        return None

    if end == -1:
        end = start + 2000  # fallback

    summary = " ".join(text[start:end].split())[:2000]
    
    return summary
    
def load_summaries(project):
    filename = f"summaries_{project['name']}.json"

    if not os.path.exists(filename):
        return []

    with open(filename, encoding="utf-8") as f:
        return json.load(f)


def save_summaries(summaries, project):
    filename = f"summaries_{project['name']}.json"

    # храним максимум 7 дней
    summaries = summaries[-7:]

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(summaries, f, ensure_ascii=False, indent=2)
        
def add_summary(summary_text, project):

    summaries = load_summaries(project)

    summaries.append({
        "text": summary_text,
        "time": datetime.now().isoformat()
    })

    save_summaries(summaries, project)
    
# =========================================================
# NO DOUBLE PDF
# =========================================================

def is_pdf_processed(file_id, project):

    filename = f"processed_files_{project['name']}.json"

    if not os.path.exists(filename):
        return False

    with open(filename) as f:
        data = json.load(f)

    return file_id in data
    
def mark_pdf_processed(file_id, project):

    filename = f"processed_files_{project['name']}.json"

    if os.path.exists(filename):
        with open(filename) as f:
            data = json.load(f)
    else:
        data = []

    if file_id not in data:
        data.append(file_id)

    with open(filename, "w") as f:
        json.dump(data, f)