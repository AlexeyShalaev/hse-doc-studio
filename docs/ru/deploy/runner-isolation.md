---
title: Изоляция и лимиты раннеров
description: Лимиты CPU, памяти и хранилища раннеров в Kubernetes, сетевая изоляция, безопасность подов, квота и проверка на кластере.
tags:
  - Развёртывание
  - Раннер
  - Безопасность
---

# Изоляция и лимиты раннеров

<p class="hds-lede">Поды сборки выполняют TeX-код пользовательских документов, поэтому в Kubernetes у них жёсткие лимиты, нет сети и ограниченный (restricted) под. Здесь перечислено, что задаёт Helm-чарт, какие есть настройки и как всё проверить.</p>

## Лимиты ресурсов

| Под | Умолчания (requests / limits) | Где менять |
|---|---|---|
| раннер (chart-раннер, `executor: docker` или `kubernetes`) | cpu 100m / 1, memory 256Mi / 2Gi, ephemeral-storage 128Mi / 2Gi | `runner.resources`, `runner.tmpSizeLimit` |
| под сборки (`executor: kubernetes`) | cpu 500m / 2, memory 1Gi / 4Gi, ephemeral-storage 1Gi / 4Gi | `runner.kubernetes.resources` |
| раннер, поставленный из админки | как у chart-раннера | `runner.installFromUi.resources` или форма установки |
| под сборки раннера, поставленного из админки | cpu 500m / 2, memory 1Gi / 4Gi | `runner.installFromUi.buildResources` или форма установки |

Почему 4Gi памяти на сборку: XeLaTeX на обычном документе (шаблон ГОСТ, десятки страниц, рисунки) занимает примерно 0,5 до 1,5 ГиБ, большие графики TikZ и растровые рисунки высокого разрешения до 3 ГиБ. Лимит оставляет запас, request (1Gi) резервирует планировщик. Эфемерное хранилище покрывает `/work` (`workSizeLimit`, 2Gi), `/tmp` (`tmpSizeLimit`, 1Gi) и логи, поэтому лимит `ephemeral-storage` держите не меньше их суммы.

### Форма установки (Kubernetes)

В «Установить раннер» блок «Лимиты ресурсов» принимает четыре необязательных лимита: CPU и память раннера, CPU и память пода сборки. Пусто значит умолчание Helm. Requests подбираются под лимит (умолчание или сам лимит, если он меньше). Бэкенд проверяет значения до выдачи токена и до создания чего-либо:

- формат: количества Kubernetes (`500m`, `2`, `512Mi`, `4Gi`);
- нижние границы: раннер 100m и 256Mi, под сборки 500m и 1Gi (ниже TeX убивается на обычных документах);
- верхние границы: `runner.installFromUi.maxCpu` (8) и `maxMemory` (16Gi).

Нарушение возвращает 422 `invalid_resources` (в деталях имя поля и причина `format`, `min` или `max`). Выбранные лимиты пишутся в журнал аудита (`runner_install.local.start`). Раннеры, поставленные раньше, сохраняют свои значения до переустановки; их поды сборки берут новый лимит ephemeral-storage из образа раннера.

### Когда сборку убили

Под сборки, убитый по памяти (`OOMKilled`, либо latexmk убит SIGKILL в живом поде), заканчивается кодом `build_out_of_memory`; под, выселенный за предел эфемерного хранилища, кодом `build_storage_exceeded`. Пользователь видит текст с обычными причинами (огромные рисунки, TikZ со слишком большим числом точек, рекурсия макросов) и что делать, администратор видит лимит в строке деталей. Это не `build_failed` и не `build_backend_unavailable`. Если в лимит упираются обычные документы, поднимите `runner.kubernetes.resources.limits.memory`.

## Сеть

| Что | Политика |
|---|---|
| Поды сборки (chart-раннер с `executor: kubernetes` и раннеры из админки) | ни входа, ни выхода: исходники и результат идут через `exec` Kubernetes API, поэтому под сборки не достанет другие поды, базу данных, metadata-сервис облака и интернет. Переключатель: `runner.kubernetes.networkPolicy.enabled` (по умолчанию включён) |
| Поды раннеров | необязательная `runner.networkPolicy.enabled` (по умолчанию выключена): исходящий доступ только к DNS (порт 53), api Студии этого релиза (порт 8000), Kubernetes API (`apiServerPorts`, по умолчанию 443 и 6443) и `extraEgress` |

Политикам нужен CNI с поддержкой NetworkPolicy (Calico, Cilium и подобные); без него они молча не действуют. Политика подов сборки включена по умолчанию, потому что сломать ничего не может: сеть этим подам не нужна. Политика раннеров выключена, потому что чарт не знает двух адресов, нужных раннеру: сервер Kubernetes API и, если объектное хранилище вне кластера или не является подом релиза, адрес S3 (раннер берёт исходники и выгружает результат по presigned-ссылкам). Неверный список отрезал бы работающие раннеры.

Как включить политику раннеров:

1. Найдите адрес API-сервера: `kubectl get endpoints kubernetes -o wide`. Впишите его в `runner.networkPolicy.apiServerCidrs` (например `["10.0.0.5/32"]`), порт в `apiServerPorts`. Если оставить пусто, политика откроет перечисленные порты на любые адреса, кроме `169.254.0.0/16` (metadata-сервис облака).
2. Добавьте хранилище в `runner.networkPolicy.extraEgress` (записи `spec.egress` дословно): например `ipBlock` и порт 443 для внешнего S3 или `namespaceSelector` с `podSelector` для MinIO в кластере. При `s3.outsideRunnerAccess: proxy` раннеры отдают результат в api, правило для S3 не нужно.
3. Добавьте правила для остального, чем пользуется раннер: внешний OnlyOffice (`runner.officeUrl`), адреса ИИ для ретрансляции.

Если в namespace релиза действует политика запрета входа по умолчанию, разрешите вход в api от подов раннеров сами.

## Безопасность подов

Поды сборки и chart-раннеры проходят Pod Security Standard restricted:

- `runAsNonRoot`, uid и gid 1000, `seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `readOnlyRootFilesystem: true` (запись идёт в ограниченные тома `emptyDir` `/work` и `/tmp`);
- без `privileged`, `hostPath`, сети и PID узла (исключение: исполнитель docker, ему нужен `docker.sock`, равный root на узле; ставьте его на выделенные узлы);
- `automountServiceAccountToken: false` у подов сборки, api (если не включена установка из админки), задания миграций и docker-раннера; раннеры Kubernetes токен сохраняют, потому что создают поды сборки, с Role только на поды одного namespace;
- `enableServiceLinks: false`, `activeDeadlineSeconds` (1800) у подов сборки, requests и limits `ephemeral-storage` везде.

Пометьте namespace меткой `pod-security.kubernetes.io/enforce=restricted`: чарт не может пометить namespace релиза, а проверка заодно остановит всё лишнее, что Студия создала бы там по ошибке.

### Права ServiceAccount Студии

С `runner.installFromUi.enabled` Студия получает одну Role в своём namespace: Deployment (`create`, `list`, `delete`; list по метке нужен, чтобы показать поставленные раннеры), Secret (`create`, `delete`, без чтения), PersistentVolumeClaim (`create`, `delete`). Нет `get` и `update` ни на что, нет Role, RoleBinding, ServiceAccount, подов и `pods/exec`, нет ClusterRole. ServiceAccount раннера Студия выбирает из чарта по фиксированному имени, его Role покрывает только поды сборки. Остаточный риск: кто может создавать Deployment в namespace, тот запустит там любой образ, поэтому включите restricted в namespace и держите переключатель installFromUi выключенным там, где общие раннеры не нужны.

## Квота и LimitRange (опция)

Для отдельного namespace сборок (`runner.kubernetes.namespace`) чарт умеет добавить ResourceQuota (`runner.kubernetes.quota`: число подов, суммарные requests и limits CPU, памяти и эфемерного хранилища) и LimitRange (`runner.kubernetes.limitRange`: умолчания контейнера и максимум). Оба выключены по умолчанию. Поды сборки задают свои requests и limits, поэтому под квоту подходят; LimitRange страхует от чужих подов в этом namespace. Когда квота выбрана, под отклоняется и сборка падает с `build_backend_unavailable` и причиной Kubernetes в деталях. Квоту в namespace релиза чарт рендерить отказывается (она ограничила бы и саму Студию). Раннеры из админки живут в namespace релиза, поэтому квота на них не действует.

## Проверка на кластере

```sh
# 1. Рендер и умолчания
helm template rel deploy/helm/hse-doc-studio -f my-values.yaml | grep -A12 'kind: NetworkPolicy'

# 2. У пода сборки есть лимиты и restricted-контекст (запустите сборку, затем в течение 1800 с)
kubectl -n <builds-ns> get pod -l hse-doc-studio/component=build -o jsonpath='{.items[0].spec.containers[0].resources}'
kubectl -n <builds-ns> auth can-i --as=system:serviceaccount:<ns>:<runner-sa> get secrets   # no

# 3. У пода сборки нет сети (нужен CNI с NetworkPolicy); оба соединения должны не удаться
kubectl -n <builds-ns> exec <build-pod> -c tex -- sh -c 'timeout 3 bash -c "echo > /dev/tcp/169.254.169.254/80"; echo rc=$?'   # rc != 0
kubectl -n <builds-ns> exec <build-pod> -c tex -- sh -c 'timeout 3 bash -c "echo > /dev/tcp/<api-pod-ip>/8000"; echo rc=$?'   # rc != 0

# 4. Права Студии
kubectl auth can-i --as=system:serviceaccount:<ns>:<release>-api create deployments -n <ns>        # yes
kubectl auth can-i --as=system:serviceaccount:<ns>:<release>-api get secrets -n <ns>               # no
kubectl auth can-i --as=system:serviceaccount:<ns>:<release>-api create roles -n <ns>              # no

# 5. Лимит памяти: документ с заведомо огромным рисунком заканчивается build_out_of_memory
kubectl -n <builds-ns> get events --field-selector reason=OOMKilling
```

Job kind в CI (`k8s-runner-kind`) запускает поды сборки под restricted на настоящем кластере; NetworkPolicy, политика раннеров и квота проверяются в CI только рендером (golden-файлы `helm template` и юнит-тесты), поэтому проверьте их на своём кластере командами выше.
