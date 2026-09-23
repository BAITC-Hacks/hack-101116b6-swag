# hack-101116b6-swag
Hackathon team repository for SWAG

## Парсер документов

`python -m src.parse data/sample --limit 10` выводит число фрагментов и первые
10 фрагментов каждого документа. Формат: `doc`, `clause` (без конечной точки),
`text` (с номером пункта), `section` (заголовок вида «3. Заголовок»).
Ненумерованный текст сохраняется с пустым `clause`; неизвестный раздел — пустая строка.
Номера пунктов распознаются и посреди строки. Автоматическая нумерация Word,
не включённая в текст абзаца, не восстанавливается.

## Данные и внешние сервисы

- `python-docx` — текст DOCX, включая таблицы в порядке документа.
- `pymupdf` — текстовый слой PDF; сканы требуют отдельного OCR.
- `openpyxl` — все листы XLSX, включая текст формул.
- TXT читается как UTF-8/BOM или Windows-1251.
- Парсер работает локально, без GPU, API-ключей и внешних сервисов.
- Реальные редакции для интеграционного теста ожидаются в `data/sample/before/`
  и `data/sample/after/`. При отсутствии файлов соответствующий тест пропускается.
- GitHub Actions запускает тесты и передаёт код проекта в Railway для сборки
  и размещения приложения. Railway CLI закреплён на версии `4.36.1` в workflow;
  локально устанавливать его для автодеплоя не требуется.

## Автодеплой на Railway из приватного репозитория

Workflow [deploy-railway.yml](.github/workflows/deploy-railway.yml) запускает
`pytest -q`, затем деплоит приложение после каждого push в `main` от любого
разработчика. Push с несколькими коммитами деплоит итоговое состояние ветки.
Рабочие ветки не деплоятся; их изменения попадут на сайт после merge в `main`.
Запустить workflow вручную можно на вкладке Actions → Test and deploy to Railway
→ Run workflow, выбрав `main`.

Подключать Railway GitHub App к чужому репозиторию не требуется: GitHub Actions
скачивает код и загружает его через Railway CLI с токеном проекта.
По [документации GitHub](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets),
repository secrets доступны для создания collaborators личного репозитория
и участникам с write-доступом в репозитории организации. GitHub Actions должен
быть разрешён в репозитории; если настройки недоступны, потребуется его владелец.

Однократная настройка:

1. В своём Railway создайте пустой проект и пустой сервис приложения.
   Источник GitHub для этого сервиса подключать не нужно: файлы передаст workflow.
2. В Railway → Project Settings → Tokens создайте **Project Token** для
   окружения `production`. Он определяет проект и окружение без `railway login`
   и `railway link`. Используйте именно project token, не account/API token.
3. Скопируйте ID сервиса приложения в Railway (Copy Service ID).
4. В общем GitHub-репозитории откройте Settings → Secrets and variables → Actions:
   - вкладка **Secrets** → New repository secret: `RAILWAY_TOKEN` — project token;
   - вкладка **Variables** → New repository variable: `RAILWAY_SERVICE_ID` — ID сервиса.
   Токен хранится только в secrets, не в коде или `.env`.
5. Закоммитьте и запушьте workflow, `Dockerfile`, `requirements.txt`, `app/`,
   `src/` и `tests/` в `main`. Railway автоматически использует корневой
   `Dockerfile`; он запускает Streamlit на `0.0.0.0:$PORT`.
6. После первого успешного деплоя в настройках сервиса Railway откройте
   Networking → Generate Domain, чтобы получить адрес приложения.

Без API-ключей приложение работает в демо-режиме. Для работы с моделью задайте
`OPENAI_API_KEY` в Variables **сервиса Railway**, а не в workflow. При необходимости
там же задайте `OPENAI_MODEL`. Для тестов API-ключи не используются.

Статус тестов и отправки смотрите в GitHub Actions, состояние приложения и логи —
в Railway. При ошибке тестов деплой не запускается. Деплои выполняются по одному;
если за время запуска поступило несколько push, GitHub сохраняет только последний
ожидающий запуск. Если сервис уже подключён напрямую к GitHub, отключите для него
прямой автодеплой, чтобы не запускать две сборки одного push.

Документация: [деплой через Railway CLI](https://docs.railway.com/cli/deploying),
[токены Railway](https://docs.railway.com/integrations/api#project-token).
