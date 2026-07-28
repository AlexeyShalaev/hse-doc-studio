---
title: Установка
tags:
  - Установка
  - Docker
description: Скрипт одной командой, ручной docker run с разбором ключевых флагов и Docker Compose с оверлеями.
---

# Установка

<p class="hds-lede">Три способа — по возрастанию контроля. Скрипт подходит почти всем. После установки приложение само встретит вас мастером первого запуска.</p>

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar"><span class="hds-shot__brand">HSE DOC STUDIO</span><span class="hds-shot__route">/setup</span></div>
    <img src="../assets/shots/setup.ru.light.png#only-light" alt="Мастер первого запуска">
    <img src="../assets/shots/setup.ru.dark.png#only-dark" alt="Мастер первого запуска">
  </div>
  <figcaption>мастер первого запуска: одна папка для работ — больше ничего настраивать не нужно</figcaption>
</figure>

## Способ 1 · Скрипт одной командой

=== "macOS / Linux"

    ```sh
    --8<-- "install-sh.txt"
    ```

=== "Windows (PowerShell)"

    ```powershell
    --8<-- "install-ps1.txt"
    ```

Скрипт ничего не спрашивает: проверяет, что Docker отвечает, скачивает образ, запускает контейнер `hse-doc-studio` и открывает браузер. Порт по умолчанию 17240 (занят — переберёт 17241…17250). Повторный запуск безопасен: существующий контейнер не пересоздаётся, папка данных не теряется.

Переменные окружения: `PORT`, `TAG`, `HSE_STUDIO_IMAGE`, `HSE_STUDIO_NAME`, в sh-версии — `DOCKER_SOCK` для Colima и Rancher Desktop:

```sh
DOCKER_SOCK="$HOME/.colima/default/docker.sock" curl -fsSL https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.sh | sh
```

## Способ 2 · Вручную, без скриптов

Одна строка, одинаковая для sh, cmd и PowerShell:

```
--8<-- "install-docker-run.txt"
```

Дальше — <http://localhost:17240> и [первый проект](first-project.md). Каталог данных намеренно не задаётся: мастер настройки спросит одну папку и сам пересоздаст контейнер с нужным `-v`.

Разбор флагов:

| Флаг | Зачем |
|---|---|
| `-e HSE_STUDIO__SERVER__PORT=8000` | На порт 8000 смотрит HEALTHCHECK образа — без переменной пересозданный контейнер вечно числится «неподнявшимся». |
| `-v /var/run/docker.sock:…` | Через сокет Студия запускает TeX Live, пересоздаёт себя после мастера и обновляется одной кнопкой. |
| `--group-add 0` | Доступ к сокету Docker: `0` хватает для Docker Desktop, **на Linux** подставьте настоящий gid — `--group-add "$(stat -c '%g' /var/run/docker.sock)"`. |
| `--add-host=host.docker.internal:host-gateway` | Доступ к сервисам на хосте — например, к нативной Ollama. |
| `-p 17240:8000` | Порт в браузере; хотите другой — поменяйте левую часть. |

!!! warning "Git Bash на Windows"
    Git Bash переписывает `/var/run/docker.sock` в путь Windows — запускайте с префиксом `MSYS_NO_PATHCONV=1` или из PowerShell.

## Способ 3 · Docker Compose

```sh
--8<-- "install-compose.txt"
```

Затем — <http://localhost:17240>. В `.env` задаются `PORT`, `TAG`, `DATA_DIR` (**обязательно абсолютный путь**), `DOCKER_GID`, `UPDATE_FEED_URL`. С заданным `DATA_DIR` мастер настройки пропускается — и сознательно не «чинит» compose-установку.

Три оверлея, которые можно наслаивать:

```sh
# собрать образ из исходников вместо GHCR (и примонтировать packs/ для живой правки шаблонов)
docker compose -f docker-compose.yml -f compose.build.yml up -d --build

# держать проекты в своей папке на хосте (включает трансляцию путей)
PROJECTS_HOST_PATH=D:/study docker compose -f docker-compose.yml -f compose.projects.yml up -d

# отдать Студии установленные в ОС шрифты (Настройки → Шрифты → Системные)
SYSTEM_FONTS_PATH=C:/Windows/Fonts docker compose -f docker-compose.yml -f compose.system-fonts.yml up -d
```

## Что дальше

Откройте <http://localhost:17240> и [создайте первый проект](first-project.md).
