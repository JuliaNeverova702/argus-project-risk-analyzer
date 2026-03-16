# ARGUS — AI Project Risk Analyzer

ARGUS — это AI-ассистент, который анализирует состояние проекта и предсказывает риски срыва сроков.

Система объединяет данные из:

- Jira (задачи, статусы, комментарии)
- Telegram (коммуникации команды)

и использует LLM для анализа.

---

## Архитектура

Jira API + Telegram API
↓
Data aggregation
↓
Context builder
↓
LLM analysis (Dify)
↓
Risk report
↓
Telegram bot

---

## Возможности

- анализ проектных рисков
- обнаружение зависимостей между разработчиками
- анализ тональности обсуждений
- выявление задач с повышенным риском

---

## Технологии

Python  
Jira REST API  
Telegram Bot API  
Dify (LLM workflows)

---

## Пример отчёта

🤖 ARGUS — утренний анализ проекта

📊 Общий риск проекта: 🟠 40%

🎯 Риски по задачам

SOFTCOMPANY-70703 — 40%
Причина: ожидание информации от разработчика

---

## Запуск

```bash
pip install -r requirements.txt
python src/argus.py
