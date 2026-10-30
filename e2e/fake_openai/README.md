# Поддельный OpenAI-совместимый сервер

Нужен живому стенду личных раннеров (`deploy/server/compose.personal.yml`, сервис `fake-openai`) и сценарию
`e2e/tests/personal.spec.ts`. Живёт только в сети `personal-net`, куда api не подключён: до модели доходит
лишь личный раннер, который объявил адрес `fake` в `HSE_RUNNER__AI_ENDPOINTS`.

- `GET /v1/models`: `fake-model`, `fake-slow`, `fake-drop`, `fake-500`, `fake-huge`;
- `POST /v1/chat/completions`: режим выбирает модель (по слову, медленно, обрыв, ошибка 500, огромный ответ), поток SSE при `stream: true`;
- `GET /stats`: число запросов, завершённых ответов и соединений, закрытых клиентом посреди потока (отмена в чате).

Только стандартная библиотека Python: образ `python:3.13-alpine` без установки зависимостей.
