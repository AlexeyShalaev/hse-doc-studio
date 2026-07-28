# Установка hse-doc-studio

Один контейнер: `ghcr.io/alexeyshalaev/hse-doc-studio` (linux/amd64 + linux/arm64).
FastAPI отдаёт и API, и собранный интерфейс. Внешних зависимостей нет — ни базы, ни облака.

Единственное требование — установленный и запущенный Docker.

Куда положить ваши файлы, приложение спросит само при первом запуске: мастер настройки
покажет выбор папки и пересоздаст контейнер с нужным `-v`. Поэтому ни скрипт, ни ручная
команда ниже каталог данных не задают.

## Установка одной строкой

**macOS / Linux**

```sh
curl -fsSL https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.sh | sh
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.ps1 | iex
```

Скрипт проверяет, что докер отвечает, скачивает образ, запускает контейнер `hse-doc-studio`,
ждёт `/health` и открывает браузер. Повторный запуск ничего не ломает: существующий
контейнер он не пересоздаёт, а поднимает, если тот остановлен.

Переопределяемые переменные окружения: `PORT`, `TAG`, `HSE_STUDIO_IMAGE`, `HSE_STUDIO_NAME`,
а в `install.sh` ещё и `DOCKER_SOCK` (для Colima и Rancher Desktop).

## Вручную, без скриптов

Одна строка, одинаковая для sh, cmd и PowerShell:

```
docker run -d --name hse-doc-studio --restart unless-stopped -p 17240:8000 -v /var/run/docker.sock:/var/run/docker.sock --group-add 0 --add-host=host.docker.internal:host-gateway -e HSE_STUDIO__SERVER__PORT=8000 ghcr.io/alexeyshalaev/hse-doc-studio:latest
```

Дальше — <http://localhost:17240> и мастер настройки.

Два флага, которые нельзя выкидывать:

* `-e HSE_STUDIO__SERVER__PORT=8000` — на 8000 смотрит HEALTHCHECK образа, а по нему мастер
  понимает, поднялся ли пересозданный контейнер. Свежие образы выставляют порт сами; на
  опубликованных раньше бэкенд слушает 17240, и без переменной настройка бесконечно
  откатывается как «неподнявшаяся».
* `-v /var/run/docker.sock:/var/run/docker.sock` — через сокет приложение запускает соседний
  контейнер с TeX Live, пересоздаёт себя после мастера и обновляется одной кнопкой.

`--group-add` обязателен: процесс внутри работает от непривилегированного `app`, а сокет
приезжает с правами владельца с хоста. Без членства в его группе любое обращение к докеру
падает с «permission denied» — приложение поднимается и выглядит рабочим, но не собирает ни
одного документа и не может настроить себя само.

`0` подходит для Docker Desktop (Windows и macOS), где сокет принадлежит `root:root`.
**На Linux** он обычно `root:docker` — подставьте настоящий gid:

```sh
docker run -d ... --group-add "$(stat -c '%g' /var/run/docker.sock)" ghcr.io/alexeyshalaev/hse-doc-studio:latest
```

В **Git Bash на Windows** ту же команду нужно предварить `MSYS_NO_PATHCONV=1`: иначе он
превратит `/var/run/docker.sock` в `C:\Program Files\Git\var\...`, и докер ответит
«Access is denied». В PowerShell и cmd такого нет.

## Порт занят

Скрипты сами берут следующий свободный (17240 → 17241 → …) и печатают, какой выбрали.
Задать порт заранее: `PORT=18500 sh install.sh` или `$env:PORT=18500; .\install.ps1`.
Вручную — поменяйте левое число в `-p 18500:8000`; правое (8000) не трогайте.

## Обновление

Проще всего — из интерфейса: «О программе» → «Обновить». Там же можно переключиться на любую
опубликованную версию, в том числе вернуться на более раннюю; проекты и настройки лежат в
вашей папке и остаются на месте. Автообновление включено по умолчанию и не начинается, пока
идёт сборка или ответ ассистента; если новая версия не поднимется — откат на предыдущую.

Руками:

```sh
docker pull ghcr.io/alexeyshalaev/hse-doc-studio:latest
docker rm -f hse-doc-studio
# затем снова скрипт или ручная команда — только не забудьте свой -v с папкой данных,
# если контейнер уже был настроен мастером
```

Проверку обновлений можно выключить целиком (`-e HSE_STUDIO__UPDATE_FEED_URL=off`) — тогда
наружу не уйдёт ни один запрос.

## Удаление

```sh
docker rm -f hse-doc-studio
docker rmi ghcr.io/alexeyshalaev/hse-doc-studio:latest
```

Папка с вашими проектами и настройками остаётся на диске — приложение её не трогает. Удалите
руками, если она больше не нужна. Соседние контейнеры, которые приложение поднимало само
(LanguageTool, Gotenberg, ONLYOFFICE, Ollama), помечены меткой:

```sh
docker rm -f $(docker ps -aq --filter label=com.hse-studio.managed=true)
```

## Альтернатива: docker compose

Кому привычнее compose — всё осталось на месте, каталог данных задаётся в `.env`, мастер
настройки в этом случае не нужен:

```sh
curl -O https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/all-in-one/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/all-in-one/.env.example
docker compose up -d
```

```
deploy/
├── install.sh                  # macOS + Linux: проверить докер → запустить → открыть браузер
├── install.ps1                 # то же для Windows PowerShell 5.1+
└── all-in-one/
    ├── docker-compose.yml      # база: готовый образ + том данных + docker.sock
    ├── compose.build.yml       # оверлей: собрать из исходников вместо pull из GHCR
    ├── compose.projects.yml    # оверлей: проекты в отдельной папке хоста
    ├── compose.system-fonts.yml# оверлей: показать шрифты, установленные в вашей ОС
    ├── Dockerfile              # ЕДИНСТВЕННЫЙ Dockerfile проекта, контекст = корень репы
    └── .env.example            # PORT / DATA_DIR / TAG / DOCKER_GID / PROJECTS_HOST_PATH / …
```

В `.env` для Linux пропишите `DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)`: compose,
в отличие от скрипта, сам его не вычислит. Оверлеи складываются, применять можно несколько
сразу:

```sh
docker compose -f deploy/all-in-one/docker-compose.yml -f deploy/all-in-one/compose.build.yml up -d --build
```

## Что стоит знать

> **Каталог данных.** Папка, которую вы назовёте в мастере, хранит проекты, настройки и
> шрифты. Это ваши документы — **бэкапьте её**.

> **Docker-сокет** root-эквивалентен на хосте. Это приемлемо для локального
> однопользовательского инструмента и обязательно для сборки документов и самообновления.

> **Соседние контейнеры** (LanguageTool, Gotenberg, ONLYOFFICE) приложение поднимает само в
> своей сети `hse-studio-net`; наружу их порты не публикуются.

> **Ollama, поставленная вами**, ищется по `host.docker.internal`. Чтобы она отвечала не
> только процессам хоста, запустите её с `OLLAMA_HOST=0.0.0.0`. Если её нет — приложение
> предложит поднять свою.

> **Версия образа.** `:latest` тянет последний релиз. Закрепитесь на конкретной
> (`TAG=0.2.0`), если нужна воспроизводимость.

Полное руководство —
**[в документации](https://alexeyshalaev.github.io/hse-doc-studio/getting-started/installation/)**.
