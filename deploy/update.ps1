# Обновление hse-doc-studio на Windows (PowerShell 5.1+) — ТЕМ ЖЕ механизмом,
# что и кнопка «Обновить» в приложении: соседний контейнер-апдейтер пересоздаёт
# студию с сохранением всех её флагов (порты, бинды, переменные), ждёт здоровья
# и САМ откатывается на прежнюю версию, если новая не поднялась. Папка данных
# не трогается; переустановка с нуля не нужна.
#
# Контракт апдейтера (стабильный, живёт в самом образе приложения):
#   python -m hse_doc_studio.infra.update.updater <контейнер> <новый образ>
#
# Файл сохранён БЕЗ BOM (см. install.ps1). Совместимость с Windows PowerShell 5.1.

$ErrorActionPreference = 'Continue'

$Image = $env:HSE_STUDIO_IMAGE
if ([string]::IsNullOrWhiteSpace($Image)) {
    $Tag = $env:TAG
    if ([string]::IsNullOrWhiteSpace($Tag)) { $Tag = 'latest' }
    $Image = "ghcr.io/alexeyshalaev/hse-doc-studio:$Tag"
}
$Name = $env:HSE_STUDIO_NAME
if ([string]::IsNullOrWhiteSpace($Name)) { $Name = 'hse-doc-studio' }
$UpdaterName = 'hse-studio-updater'

# Язык сообщений: HSE_STUDIO_LANG=ru — русский, иначе английский.
$LangRu = ("$env:HSE_STUDIO_LANG" -match '^(?i)ru')

function Loc([string]$Ru, [string]$En) {
    if ($LangRu) { return $Ru }
    return $En
}

function Say([string]$Message) {
    Write-Host $Message
}

function Fail([string]$Message) {
    Write-Host "$(Loc 'ошибка' 'error'): $Message" -ForegroundColor Red
    throw (Loc 'обновление прервано' 'update aborted')
}

function Invoke-Docker {
    param([string[]]$DockerArgs)
    $output = (& docker @DockerArgs 2>&1 | Out-String)
    return [pscustomobject]@{
        Code   = $LASTEXITCODE
        Output = $output
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail (Loc 'не найден docker.' 'docker not found.')
}
$info = Invoke-Docker @('info')
if ($info.Code -ne 0) {
    Fail (Loc 'демон докера не отвечает — запустите Docker Desktop и повторите.' `
        'the docker daemon is not responding — start Docker Desktop and retry.')
}

$exists = Invoke-Docker @('inspect', $Name)
if ($exists.Code -ne 0) {
    Fail ((Loc "контейнер $Name не найден. Сначала установка:" "container $Name not found. Install first:") +
        "`n    irm https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.ps1 | iex")
}

$current = Invoke-Docker @('inspect', '-f', '{{.Config.Image}}', $Name)
Say (Loc "текущий образ: $($current.Output.Trim())" "current image: $($current.Output.Trim())")
Say (Loc "скачиваю $Image" "pulling $Image")
$pull = Invoke-Docker @('pull', $Image)
if ($pull.Code -ne 0) {
    # Неудачный pull не смертелен: апдейтер попробует скачать сам.
    Say (Loc 'скачать заранее не вышло — апдейтер попробует сам.' `
        'pre-pull failed — the updater will retry on its own.')
}

# Остатки прошлого запуска (его логи больше не нужны).
Invoke-Docker @('rm', '-f', $UpdaterName) | Out-Null

Say (Loc 'запускаю апдейтер — пересоздание с сохранением настроек, при неудаче автооткат.' `
    'starting the updater — recreation with settings preserved, automatic rollback on failure.')
$run = Invoke-Docker @(
    'run', '-d',
    '--name', $UpdaterName,
    '--label', 'com.hse-studio.managed=true',
    '-v', '/var/run/docker.sock:/var/run/docker.sock',
    '--group-add', '0',
    $Image,
    'python', '-m', 'hse_doc_studio.infra.update.updater', $Name, $Image
)
if ($run.Code -ne 0) {
    Fail ((Loc 'апдейтер не запустился:' 'failed to start the updater:') + "`n$($run.Output.Trim())")
}

# Логи апдейтера в реальном времени; поток заканчивается вместе с ним.
& docker logs -f $UpdaterName 2>&1 | Write-Host
$wait = Invoke-Docker @('wait', $UpdaterName)
$rc = $wait.Output.Trim()

$final = Invoke-Docker @('inspect', '-f', '{{.Config.Image}}', $Name)
$portOut = Invoke-Docker @('port', $Name, '8000/tcp')
$port = $null
if ($portOut.Code -eq 0) {
    $line = ($portOut.Output -split "`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
    if ($line) { $port = ($line.Trim() -split ':')[-1] }
}

if ($rc -eq '0' -and $final.Code -eq 0) {
    Say ""
    Say (Loc "готово: $Name теперь на $($final.Output.Trim())" "done: $Name is now on $($final.Output.Trim())")
    if ($port) { Say "  http://localhost:$port" }
}
else {
    Fail ((Loc "обновление не удалось (апдейтер завершился с кодом $rc) — приложение осталось/откатилось на прежнюю версию." `
        "update failed (updater exited with code $rc) — the app stayed on / rolled back to the previous version.") +
        "`n  " + (Loc "Подробности: docker logs $UpdaterName" "Details: docker logs $UpdaterName"))
}
