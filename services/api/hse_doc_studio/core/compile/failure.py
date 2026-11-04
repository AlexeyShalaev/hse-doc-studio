"""Причина неудачной сборки: стабильный код, сырая деталь и текст «что делать» на языке интерфейса.

Код приходит от раннера (`JobError.code`), от сервера (постановка, квота, срок) или от самой сборки
(`build_failed`: LaTeX вернул ошибку, подробности в логе). Текст нужен и записи сборки, и строке журнала,
поэтому каталог один, а язык берётся из текущего контекста.
"""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.enums import Lang

BUILD_FAILED = "build_failed"
PDF_MISSING = "pdf_missing"
DISK_FULL = "disk_full"
UNKNOWN = "unknown"

# Сборку остановили руками или заменили более новой: не сбой окружения.
CANCELLED = "cancelled"
SUPERSEDED = "superseded"
# Студию или сервер перезапустили, пока шла сборка: запись закрыта при старте.
RESTARTED = "restarted"

_DETAIL_LIMIT = 2000

_TEXTS: dict[str, tuple[str, str]] = {
    BUILD_FAILED: (
        (
            "LaTeX завершился с ошибкой. Откройте журнал ниже: первая строка, начинающаяся с «!» или с имени "
            "файла и номера строки, указывает место. Исправьте исходник и соберите снова."
        ),
        (
            "LaTeX finished with an error. Open the log below: the first line starting with “!” or with a "
            "file name and line number points at the spot. Fix the source and build again."
        ),
    ),
    PDF_MISSING: (
        (
            "Сборка прошла, но PDF не появился. Проверьте, что документ выпускает PDF и \\begin{document} не "
            "закомментирован."
        ),
        (
            "The build finished but no PDF was produced. Check that the document produces a PDF and that "
            "\\begin{document} is not commented out."
        ),
    ),
    "image_missing": (
        (
            "На машине, которая собирает, не установлен образ TeX Live. Откройте «Настройки → Компилятор → "
            "Образы» на этой машине и нажмите «Установить» (или выполните docker pull для образа из "
            "сообщения), затем соберите снова."
        ),
        (
            "The TeX Live image is not installed on the machine that builds. Open “Settings → Compiler → "
            "Images” on that machine and press “Install” (or docker pull the image from the message), then "
            "build again."
        ),
    ),
    "docker_unavailable": (
        (
            "Docker на машине, которая собирает, недоступен. Запустите Docker Desktop или демон docker, "
            "проверьте доступ к docker.sock (группа сокета, DOCKER_GID) и соберите снова."
        ),
        (
            "Docker is not available on the machine that builds. Start Docker Desktop or the docker daemon, "
            "check access to docker.sock (socket group, DOCKER_GID) and build again."
        ),
    ),
    "build_backend_unavailable": (
        (
            "Исполнитель сборки (Kubernetes) отказал: нет прав, квоты, узла или пода. Администратору: "
            "проверьте события пространства имён раннера и права его сервисной учётной записи."
        ),
        (
            "The build executor (Kubernetes) refused: no permissions, quota, node or pod. Administrator: "
            "check the events of the runner namespace and the permissions of its service account."
        ),
    ),
    "blob_unavailable": (
        (
            "Раннер не смог получить исходники проекта с сервера. Проверьте, что раннер видит адрес сервера и"
            " хранилища (режим proxy для внешних раннеров, публичный адрес S3), и соберите снова."
        ),
        (
            "The runner could not fetch the project sources from the server. Check that the runner can reach "
            "the server and storage addresses (proxy mode for outside runners, public S3 address) and build "
            "again."
        ),
    ),
    "storage_unreachable": (
        (
            "Раннер собрал PDF, но не смог выгрузить его в хранилище сервера: адрес хранилища из ссылки "
            "недоступен с этой машины. Администратору: включите режим proxy для внешних раннеров или задайте "
            "публичный адрес S3."
        ),
        (
            "The runner built the PDF but could not upload it to the server storage: the storage address in "
            "the link is not reachable from that machine. Administrator: enable proxy mode for outside "
            "runners or set the public S3 address."
        ),
    ),
    "artifact_upload_failed": (
        (
            "Раннер собрал PDF, но сервер не принял выгрузку результата. Повторите сборку; если не помогает, "
            "администратору: проверьте журнал api (размер файла, лимит выходов, место в хранилище)."
        ),
        (
            "The runner built the PDF but the server did not accept the upload. Build again; if it does not "
            "help, administrator: check the api log (file size, output limit, storage space)."
        ),
    ),
    "artifact_invalid": (
        ("Сервер отклонил выгруженный PDF (не совпали размер или хеш, либо файл слишком большой). Повторите сборку."),
        ("The server rejected the uploaded PDF (size or hash mismatch, or the file is too large). Build again."),
    ),
    "executor_crashed": (
        "Раннер упал во время сборки. Подробности в журнале раннера на его машине; повторите сборку.",
        "The runner crashed during the build. Details are in the runner log on its machine; build again.",
    ),
    "compile_crashed": (
        ("Сборка оборвалась из-за внутренней ошибки Студии. Подробности в журнале Студии; повторите сборку."),
        ("The build was interrupted by an internal Studio error. Details are in the Studio log; build again."),
    ),
    "handler_crashed": (
        "Сборка оборвалась из-за внутренней ошибки. Подробности в журнале Студии; повторите сборку.",
        "The build was interrupted by an internal error. Details are in the Studio log; build again.",
    ),
    DISK_FULL: (
        (
            "На машине, которая собирает, закончилось место на диске. Освободите место (папка данных раннера,"
            " образы и тома docker: docker system prune) и соберите снова."
        ),
        (
            "The machine that builds is out of disk space. Free some space (the runner data folder, docker "
            "images and volumes: docker system prune) and build again."
        ),
    ),
    "timed_out": (
        (
            "Сборка не уложилась в отведённое время и остановлена. Проверьте журнал: возможно, LaTeX "
            "зациклился; администратор может увеличить срок сборки в настройках установки."
        ),
        (
            "The build did not finish in time and was stopped. Check the log: LaTeX may be stuck in a loop; "
            "the administrator can raise the build timeout in the installation settings."
        ),
    ),
    "job_timeout": (
        (
            "Сборка не уложилась в отведённое время и остановлена. Проверьте журнал: возможно, LaTeX "
            "зациклился; администратор может увеличить срок сборки в настройках установки."
        ),
        (
            "The build did not finish in time and was stopped. Check the log: LaTeX may be stuck in a loop; "
            "the administrator can raise the build timeout in the installation settings."
        ),
    ),
    "runner_lost": (
        (
            "Раннер пропал посреди сборки, и повторов не осталось. Проверьте, что машина раннера включена и "
            "online, и соберите снова."
        ),
        (
            "The runner disappeared in the middle of the build and no retries are left. Check that the runner"
            " machine is on and online, and build again."
        ),
    ),
    "lease_lost": (
        "Раннер потерял связь с сервером посреди сборки. Проверьте сеть раннера и соберите снова.",
        (
            "The runner lost its connection to the server in the middle of the build. Check the runner "
            "network and build again."
        ),
    ),
    "runner_shutdown": (
        "Раннер остановили во время сборки. Запустите его и соберите снова.",
        "The runner was stopped during the build. Start it and build again.",
    ),
    "job_lost": (
        "Сервер потерял запись сборки в очереди. Соберите снова.",
        "The server lost the build record in the queue. Build again.",
    ),
    "staging_failed": (
        (
            "Сервер не смог подготовить проект к сборке (собрать манифест файлов и загрузить его в "
            "хранилище). Администратору: проверьте журнал api и доступность хранилища."
        ),
        (
            "The server could not prepare the project for the build (gather the file manifest and upload it "
            "to storage). Administrator: check the api log and storage availability."
        ),
    ),
    "quota_exceeded": (
        (
            "Исчерпана квота сборок. Дождитесь сброса счётчика или попросите администратора поднять предел; "
            "сборка на личном раннере квоту не тратит."
        ),
        (
            "The build quota is used up. Wait for the counter to reset or ask the administrator to raise the "
            "limit; building on a personal runner does not spend the quota."
        ),
    ),
    "no_runners": (
        (
            "Сейчас ни один раннер сборки не подключён. Подключите личный раннер (локальную Студию) или "
            "обратитесь к администратору сервера."
        ),
        (
            "No build runner is connected right now. Connect a personal runner (a local Studio) or contact "
            "the server administrator."
        ),
    ),
    "no_runner_for_tags": (
        (
            "Нет раннера с нужными возможностями (например, TeX). Подключите личный раннер с Docker или "
            "обратитесь к администратору."
        ),
        (
            "There is no runner with the required capabilities (for example TeX). Connect a personal runner "
            "with Docker or contact the administrator."
        ),
    ),
    CANCELLED: (
        "Сборку отменили до завершения. Соберите снова, когда будете готовы.",
        "The build was cancelled before it finished. Build again when you are ready.",
    ),
    "idle_timeout": (
        (
            "Сборка молчала дольше предела и остановлена. На новом образе TeX Live первая сборка молча строит кэш "
            "шрифтов и может идти несколько минут: соберите ещё раз (кэш сохраняется в томе docker), а если "
            "повторяется, увеличьте HSE_STUDIO__COMPILE__IDLE_TIMEOUT_S (для раннера HSE_RUNNER__TEX_IDLE_TIMEOUT_S)."
        ),
        (
            "The build was silent for longer than the limit and was stopped. On a new TeX Live image the first build "
            "silently builds the font cache and can take several minutes: build again (the cache is kept in a docker "
            "volume), and if it repeats, raise HSE_STUDIO__COMPILE__IDLE_TIMEOUT_S (HSE_RUNNER__TEX_IDLE_TIMEOUT_S "
            "for a runner)."
        ),
    ),
    "docker_exec_failed": (
        ("Не удалось запустить docker. Проверьте, что docker установлен, доступен процессу Студии и демон запущен."),
        (
            "Could not start docker. Check that docker is installed, available to the Studio process and the "
            "daemon is running."
        ),
    ),
    "host_path_unmapped": (
        (
            "Папка проекта не видна docker-демону: путь внутри контейнера Студии не сопоставлен с путём хоста. "
            "Проверьте, что папка данных смонтирована в контейнер (DATA_DIR) и HSE_STUDIO__HOST_DATA_DIR задан верно."
        ),
        (
            "The project folder is not visible to the docker daemon: the path inside the Studio container is not "
            "mapped to a host path. Check that the data folder is mounted into the container (DATA_DIR) and that "
            "HSE_STUDIO__HOST_DATA_DIR is correct."
        ),
    ),
    "build_dir_failed": (
        (
            "Не удалось создать папку сборки в проекте (права или место на диске). Проверьте права на папку "
            "проекта и свободное место."
        ),
        (
            "Could not create the build folder in the project (permissions or disk space). Check the project folder "
            "permissions and free space."
        ),
    ),
    "unsupported_engine": (
        "Движок LaTeX документа не поддерживается. Выберите xelatex, pdflatex или lualatex.",
        "The document's LaTeX engine is not supported. Choose xelatex, pdflatex or lualatex.",
    ),
    RESTARTED: (
        ("Студию или сервер перезапустили, пока шла сборка, и она оборвалась. Соберите документ снова."),
        (
            "The Studio or the server was restarted while the build was running, and the build was interrupted. "
            "Build the document again."
        ),
    ),
    SUPERSEDED: (
        "Сборку заменила более новая сборка того же документа. Результат смотрите в новой сборке.",
        "A newer build of the same document replaced this one. See the result in the newer build.",
    ),
    "output_not_allowed": (
        "Сервер не принял файл результата: путь не разрешён для сборки. Сообщите администратору.",
        ("The server did not accept the result file: the path is not allowed for a build. Tell the administrator."),
    ),
    "output_unsafe_path": (
        "Сервер не принял файл результата: небезопасный путь. Сообщите администратору.",
        "The server did not accept the result file: unsafe path. Tell the administrator.",
    ),
    "output_missing": (
        "Файл результата пропал по дороге от раннера к серверу. Повторите сборку.",
        "The result file was lost between the runner and the server. Build again.",
    ),
    "output_mismatch": (
        ("Файл результата повредился по дороге от раннера к серверу (не совпали размер или хеш). Повторите сборку."),
        ("The result file was corrupted between the runner and the server (size or hash mismatch). Build again."),
    ),
    "output_changed": (
        "Файл результата изменился на раннере до выгрузки. Повторите сборку.",
        "The result file changed on the runner before upload. Build again.",
    ),
    "apply_failed": (
        (
            "Сервер не смог положить PDF в проект (диск, права или хранилище). Администратору: проверьте "
            "журнал api и место на томе проектов."
        ),
        (
            "The server could not place the PDF into the project (disk, permissions or storage). "
            "Administrator: check the api log and free space on the projects volume."
        ),
    ),
    "manifest_error": (
        "Проект не удалось подготовить к сборке: ошибка в наборе файлов. Подробности ниже.",
        "The project could not be prepared for the build: error in the file set. Details below.",
    ),
    "manifest_file_too_large": (
        (
            "В проекте есть файл больше допустимого размера для облачной сборки. Уберите или уменьшите его "
            "(путь в подробностях) и соберите снова."
        ),
        (
            "The project has a file larger than the cloud build allows. Remove or shrink it (path in the "
            "details) and build again."
        ),
    ),
    "manifest_too_large": (
        "Проект слишком велик для облачной сборки. Уберите крупные файлы из проекта и соберите снова.",
        "The project is too large for a cloud build. Remove large files from the project and build again.",
    ),
    "manifest_file_missing": (
        "Файл проекта пропал во время подготовки к сборке. Соберите снова.",
        "A project file disappeared while the build was being prepared. Build again.",
    ),
    "manifest_file_changed": (
        "Файл проекта изменился во время подготовки к сборке. Соберите снова.",
        "A project file changed while the build was being prepared. Build again.",
    ),
    "manifest_unsafe_path": (
        ("В проекте есть файл с небезопасным путём. Переименуйте его (путь в подробностях) и соберите снова."),
        "The project has a file with an unsafe path. Rename it (path in the details) and build again.",
    ),
    UNKNOWN: (
        (
            "Причина сбоя не определена. Подробности ниже и в журнале; если повторная сборка не помогает, "
            "сообщите администратору код ошибки."
        ),
        (
            "The cause of the failure is unknown. Details are below and in the log; if building again does "
            "not help, tell the administrator the error code."
        ),
    ),
}


@dataclass(frozen=True)
class CompileFailure:
    """Причина неудачной сборки: код, сырая деталь (путь, исключение раннера) и человеческий текст."""

    code: str
    detail: str | None = None

    def message(self, lang: Lang) -> str:
        return failure_message(self.code, lang)


def failure_message(code: str, lang: Lang) -> str:
    """Текст «что произошло и что делать» по коду; неизвестный код получает общий текст."""
    ru, en = _TEXTS.get(code) or _TEXTS[UNKNOWN]
    return en if lang is Lang.en else ru


def clip_detail(detail: str | None) -> str | None:
    """Сырая деталь для записи: без нулевых символов (Postgres их не принимает) и не длиннее предела."""
    if not detail:
        return None
    cleaned = detail.replace("\x00", "")[:_DETAIL_LIMIT].strip()
    return cleaned or None


def failure_log_block(failure: CompileFailure, lang: Lang) -> str:
    """Строки журнала, которыми закрывается упавшая сборка: код, текст и деталь."""
    lines = [f"[error] {failure.code}: {failure.message(lang)}"]
    if failure.detail:
        lines.append(f"[error] {failure.detail}")
    return "\n".join(lines)
