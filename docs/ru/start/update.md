---
title: Обновление и удаление
description: Обновление одной кнопкой с автоматическим откатом и чистое удаление; папка данных не трогается никогда.
tags:
  - Обновление
  - Docker
---

# Обновление и удаление

<p class="hds-lede">Студия обновляет себя сама. Папка данных не трогается ни при обновлении, ни при удалении.</p>

## Обновление

- Настройки → **О программе**: кнопка обновления, «Что нового» и переключение на любую опубликованную версию, включая откат.
- Обновлятор пересоздаёт контейнер со всеми вашими флагами и **сам откатывается**, если новая версия не поднялась.
- Автообновление включено по умолчанию и не стартует во время сборки; отключается там же. Полностью выключить обращения к фиду: `HSE_STUDIO__UPDATE_FEED_URL=off`.

### Обновление вручную { #manual-update }

Если интерфейс недоступен: скачать свежий образ, удалить контейнер, поставить заново. Папка данных не трогается — мастер узнает прежнюю установку и предложит её же.

=== "macOS / Linux"

    ```sh
    docker pull ghcr.io/alexeyshalaev/hse-doc-studio:latest
    docker rm -f hse-doc-studio
    curl -fsSL https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.sh | HSE_STUDIO_LANG=ru sh
    ```

=== "Windows (PowerShell)"

    ```powershell
    docker pull ghcr.io/alexeyshalaev/hse-doc-studio:latest
    docker rm -f hse-doc-studio
    $env:HSE_STUDIO_LANG='ru'; irm https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.ps1 | iex
    ```

## Удаление

```sh
docker rm -f hse-doc-studio
docker rmi ghcr.io/alexeyshalaev/hse-doc-studio:latest
# служебные соседи (TeX Live, LanguageTool, ONLYOFFICE, Gotenberg, Ollama)
docker rm -f $(docker ps -aq --filter label=com.hse-studio.managed=true)
```

Образы можно удалить и заранее — Настройки → **Диск**. Папка данных остаётся: укажите её при повторной установке, и всё вернётся.
