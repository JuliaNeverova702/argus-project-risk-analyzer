# ARGUS Architecture

ARGUS — это система анализа рисков проекта на основе данных из инструментов разработки.

## Data Flow
Jira API
↓
Issue Loader

Telegram Bot API
↓
Message Collector

↓

Context Builder
(объединение данных)

↓

LLM Analysis (Dify)

↓

Risk Report Generator

↓

Telegram Bot

## Компоненты

### Jira Loader

Получает:

- задачи
- статусы
- исполнителей
- комментарии

### Telegram Collector

Собирает:

- сообщения команды
- обсуждения задач

### Context Builder

Формирует общий контекст проекта.

### LLM Analysis

Модель анализирует:

- блокеры
- зависимости
- риски задержек

### Report Generator

Создаёт отчёт и отправляет его в Telegram.
