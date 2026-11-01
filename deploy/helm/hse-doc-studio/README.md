# Helm-чарт HSE Doc Studio

Серверный режим в Kubernetes: api (одна реплика, стратегия `Recreate`), по желанию раннер задач.
Postgres и S3-совместимое хранилище внешние, в чарт они не входят. Том исходников проектов
(`/data`) это PVC `ReadWriteOnce`: поэтому реплика одна и rolling-обновления нет.

## Установка

```bash
helm install studio deploy/helm/hse-doc-studio -f my-values.yaml
```

Минимум в `my-values.yaml`: `publicUrl`, `database.dsn`, `s3.*`, `secrets.secretsKey`,
`secrets.runnerBootstrapToken`. Рекомендуется не класть секреты в values, а завести Secret
заранее и указать `secrets.existingSecret`. Ключи Secret:
`dsn`, `secrets-key`, `s3-access-key`, `s3-secret-key`, `runner-bootstrap-token`,
необязательные `smtp-password`, `health-token`, `metrics-token`.

Ключ `secrets.secretsKey` (Fernet) нельзя терять: без него сохранённые секреты нечитаемы.

## Миграции

На первой установке схему создаёт сам api под advisory-локом. При `helm upgrade` перед заменой api
выполняется Job `hse-doc-studio db upgrade` (hook `pre-upgrade`), api после этого стартует без
автомиграции. Job берёт Secret предыдущей версии выпуска: меняя секреты, обновляйте их отдельно от версии образа
или используйте `secrets.existingSecret`. Отключить: `migrations.enabled=false` (тогда мигрирует api).

## Ingress и долгий опрос

Раннер держит запрос опроса до 25 секунд. Аннотации по умолчанию рассчитаны на ingress-nginx
(`proxy-read-timeout: 75`, `proxy-buffering: off`). Для другого контроллера задайте
`ingress.annotations` с read-timeout не меньше 60 секунд и выключенной буферизацией.

## Раннер

Все поды работают от числового uid/gid из `podSecurityContext` (10001, как пользователь `app` в образе). Каталог `runner.dataDir` на узле создаётся от root, поэтому initContainer `fix-data-dir` выдаёт его этому пользователю.

Раннер всегда в одной реплике (`runner.replicas` не больше 1): hostPath и токен регистрации одноразовые общие. Из-за `docker.sock` и `chown` в initContainer его под не проходит Pod Security Standard restricted, api и migrate проходят.

`runner.enabled=true` запускает раннер с `hostPath` на `docker.sock` узла. Сокет эквивалентен root
на узле: используйте выделенные узлы (`runner.nodeSelector`, `runner.tolerations`). Раннер-под на задачу
относится к следующим этапам.

## Проверка

```bash
helm lint deploy/helm/hse-doc-studio -f deploy/helm/hse-doc-studio/ci/values-test.yaml --strict
cd services/api && uv run pytest tests/unit/test_helm_chart.py   # UPDATE_GOLDEN=1 обновляет эталон рендера
```
