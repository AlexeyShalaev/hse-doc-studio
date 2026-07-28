# Запуск hse-doc-studio на Windows (PowerShell 5.1+).
#
# Скрипт намеренно ничего не спрашивает. Каталог данных, права на docker-сокет и
# переменные окружения переехали внутрь продукта: контейнер поднимается БЕЗ
# единого бинда, показывает мастер первоначальной настройки, спрашивает одну
# папку и пересоздаёт себя сам. Здесь остаётся три шага: жив ли докер —
# запустить — открыть браузер.
#
# Совместимость с Windows PowerShell 5.1: без тернарного оператора, ??, ?. и
# прочего синтаксиса PowerShell 7 — на свежей Windows 5.1 по-прежнему то, что
# открывается по «PowerShell» из меню Пуск.

# $ErrorActionPreference намеренно НЕ 'Stop': в 5.1 вывод нативной программы в
# stderr при перенаправлении 2>&1 превращается в терминирующую ошибку, и скрипт
# падал бы на первом же предупреждении докера. Коды возврата проверяем руками.
$ErrorActionPreference = 'Continue'

# Образ и тег переопределяются переменными окружения — тем же способом, что и в
# docker-compose.yml, чтобы обе установки настраивались одинаково.
$Image = $env:HSE_STUDIO_IMAGE
if ([string]::IsNullOrWhiteSpace($Image)) {
    $Tag = $env:TAG
    if ([string]::IsNullOrWhiteSpace($Tag)) { $Tag = 'latest' }
    $Image = "ghcr.io/alexeyshalaev/hse-doc-studio:$Tag"
}
$Name = $env:HSE_STUDIO_NAME
if ([string]::IsNullOrWhiteSpace($Name)) { $Name = 'hse-doc-studio' }
$FirstPort = 17240
if (-not [string]::IsNullOrWhiteSpace($env:PORT)) { $FirstPort = [int]$env:PORT }

# Сколько соседних портов пробовать, если наш занят.
$PortAttempts = 10
# Первый старт дольше обычного: приложение раскладывает пак шаблонов и
# проверяет докер.
$HealthTimeoutSec = 120
$HealthPollSec = 2

function Say([string]$Message) {
    Write-Host $Message
}

function Fail([string]$Message) {
    Write-Host "ошибка: $Message" -ForegroundColor Red
    # throw, а не exit: скрипт чаще всего запускают как `irm ... | iex`, то есть
    # прямо в сессии пользователя, и `exit` закрыл бы окно вместе с только что
    # напечатанной причиной отказа. Необработанное исключение и видно, и даёт
    # ненулевой код возврата, когда скрипт запущен файлом.
    throw 'установка прервана'
}

# Единственный способ дозваться нативной программы и её stderr в 5.1: слить
# потоки и превратить в строку.
function Invoke-Docker {
    param([string[]]$DockerArgs)
    $output = (& docker @DockerArgs 2>&1 | Out-String)
    return [pscustomobject]@{
        Code   = $LASTEXITCODE
        Output = $output
    }
}

# ── 1. Докер ────────────────────────────────────────────────────────────────

function Test-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Fail "не найден docker. Поставьте Docker Desktop: https://www.docker.com/products/docker-desktop/"
    }
    # `docker info`, а не `docker version`: второй отвечает и без демона —
    # клиент печатает свою версию и молча выходит с нулём.
    $info = Invoke-Docker @('info')
    if ($info.Code -ne 0) {
        Fail ("демон докера не отвечает — запустите Docker Desktop и дождитесь, " +
            "пока он станет зелёным.`n$($info.Output.Trim())")
    }
}

# ── 2. Запуск ───────────────────────────────────────────────────────────────

function Start-AppContainer {
    param([int]$HostPort)

    # --group-add 0 обязателен и здесь. Docker Desktop отдаёт сокет как
    # root:root, а процесс внутри работает от непривилегированного `app`
    # (uid 100, gid 101) — группы 0 у него НЕТ. Без этого флага любое обращение
    # к докеру падает с «permission denied»: приложение поднимается и выглядит
    # рабочим, но не собирает ни одного документа и не может настроить себя само.
    # Проверено живым запуском: без флага мастер сообщает socket_permission.
    #
    # Каталог данных НЕ монтируем: его назовёт пользователь в мастере, после чего
    # приложение пересоздаст себя с этим -v само.
    #
    # HSE_STUDIO__SERVER__PORT=8000 передаём явно, хотя свежий образ выставляет
    # его и сам: на 8000 смотрит HEALTHCHECK, а по его результату мастер
    # настройки решает, поднялся ли пересозданный контейнер. Образы,
    # опубликованные до этой правки, слушают 17240 (порт нативного запуска) и без
    # переменной остаются вечно unhealthy — настройка на них откатывалась бы.
    return Invoke-Docker @(
        'run', '-d',
        '--name', $Name,
        '--restart', 'unless-stopped',
        '-p', "$($HostPort):8000",
        '-v', '/var/run/docker.sock:/var/run/docker.sock',
        '--group-add', '0',
        '--add-host=host.docker.internal:host-gateway',
        '-e', 'HSE_STUDIO__SERVER__PORT=8000',
        $Image
    )
}

# Порт хоста, на котором контейнер реально опубликован. Спрашиваем докер, а не
# помним своё: контейнер мог остаться от прошлого запуска с другим портом.
function Get-PublishedPort {
    $result = Invoke-Docker @('port', $Name, '8000/tcp')
    if ($result.Code -ne 0) { return $null }
    $line = ($result.Output -split "`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
    if (-not $line) { return $null }
    return ($line.Trim() -split ':')[-1]
}

function Test-ContainerExists {
    $result = Invoke-Docker @('inspect', $Name)
    return ($result.Code -eq 0)
}

function Test-ContainerRunning {
    $result = Invoke-Docker @('inspect', '-f', '{{.State.Running}}', $Name)
    return ($result.Code -eq 0 -and $result.Output.Trim() -eq 'true')
}

# ── 3. Здоровье и браузер ───────────────────────────────────────────────────

function Wait-Healthy {
    param([int]$HostPort)

    $deadline = (Get-Date).AddSeconds($HealthTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$HostPort/health" `
                -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) { return $true }
        }
        catch {
            # Пока приложение поднимается, отказ соединения — норма.
        }
        # Упавший контейнер здоровым уже не станет — ждать таймаут незачем.
        if (-not (Test-ContainerRunning)) { return $false }
        Start-Sleep -Seconds $HealthPollSec
    }
    return $false
}

function Complete-Install {
    param([int]$HostPort)

    $url = "http://localhost:$HostPort"
    if (Wait-Healthy -HostPort $HostPort) {
        Say "приложение отвечает."
    }
    else {
        Say "приложение не ответило за $HealthTimeoutSec с. Посмотрите логи: docker logs $Name"
    }

    try {
        Start-Process $url | Out-Null
    }
    catch {
        Say "браузер открыть не удалось — откройте адрес вручную."
    }

    Say ""
    Say "  $url"
    Say ""
    Say "При первом запуске приложение спросит папку для ваших файлов и перезапустится"
    Say "само — вкладку можно не закрывать, она дождётся."
    Say ""
    Say "  логи:       docker logs -f $Name"
    Say "  остановить: docker stop $Name"
    Say "  удалить:    docker rm -f $Name"
}

# ── Сценарий ────────────────────────────────────────────────────────────────

Test-Docker

# Уже установлено — не пересоздаём молча: у существующего контейнера может быть
# выбранная пользователем папка данных, и потерять её из-за повторного запуска
# скрипта было бы худшим, что этот скрипт умеет.
if (Test-ContainerExists) {
    if (Test-ContainerRunning) {
        Say "контейнер $Name уже запущен."
    }
    else {
        Say "контейнер $Name существует, но остановлен — запускаю."
        $started = Invoke-Docker @('start', $Name)
        if ($started.Code -ne 0) {
            Fail "не удалось запустить существующий контейнер:`n$($started.Output.Trim())"
        }
    }
    $runningPort = Get-PublishedPort
    if (-not $runningPort) {
        Fail ("контейнер $Name запущен без публикации порта — снаружи он недоступен.`n" +
            "  Пересоздайте его: docker rm -f $Name, затем повторите скрипт.")
    }
    Say "чтобы поставить заново с нуля: docker rm -f $Name, затем повторите скрипт."
    Complete-Install -HostPort ([int]$runningPort)
}
else {
    Say "скачиваю образ $Image"
    $pull = Invoke-Docker @('pull', $Image)
    if ($pull.Code -ne 0) {
        $local = Invoke-Docker @('image', 'inspect', $Image)
        if ($local.Code -eq 0) {
            Say "обновить образ не удалось, запускаю уже скачанный."
        }
        else {
            Fail "не удалось скачать образ ${Image}:`n$($pull.Output.Trim())"
        }
    }

    $port = $FirstPort
    $attempt = 1
    while ($true) {
        $run = Start-AppContainer -HostPort $port
        if ($run.Code -eq 0) { break }

        # Контейнер, не сумевший опубликовать порт, остаётся в состоянии Created и
        # держит имя — следующая попытка упала бы уже на занятом имени.
        Invoke-Docker @('rm', '-f', $Name) | Out-Null

        # «Ports are not available … forbidden by its access permissions» — это
        # Windows: диапазон отдан Hyper-V или WinNAT, порт формально свободен, но
        # занять его нельзя. Лечится тем же — следующим портом.
        $busy = $run.Output -match 'address already in use|port is already allocated|Ports are not available'
        if (-not $busy) {
            Fail "docker run не смог запустить контейнер:`n$($run.Output.Trim())"
        }
        $attempt++
        if ($attempt -gt $PortAttempts) {
            Fail ("порты с $FirstPort по $port заняты. Освободите один или задайте свой:`n" +
                "    `$env:PORT=18500; .\install.ps1")
        }
        $port++
        Say "порт занят, пробую $port"
    }

    Say "контейнер $Name запущен на порту $port."
    Complete-Install -HostPort $port
}
