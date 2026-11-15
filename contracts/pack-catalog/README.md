# Контракт «Каталогов паков»

Каталоги паков установки (`docs/design/template-studio.md`, 10.3 и 10.4, срез T17): подключённые паки сверх
вшитых в образ. Источник это git (адрес, папка паков, тег, ветка или sha, доступ git), загруженный архив (.zip или
.tar.gz, закрытые контуры) или папка (только локально, «Подключить к каталогу этой Студии» в Студии шаблонов).

Эталоны `fixtures/<Модель>/*.json` сверяет с моделями `services/api/hse_doc_studio/api/schemas/pack_catalog.py`
тест `tests/unit/contract/test_pack_catalog_contract.py`, клиент разбирает те же эталоны своими схемами. Коды
ошибок `error_codes.json` совпадают с `core/pack_catalog/errors.py` по порядку; тело ошибки `{detail, code, ...}`.
Сбои git источника идут кодами `contracts/git-sync/error_codes.json`.

## Маршруты

| Метод и путь | Тело | Ответ |
|---|---|---|
| `GET /api/admin/pack-catalog` | | `CatalogOverview` |
| `POST /api/admin/pack-catalog/sources` | `CreateGitSourceRequest` | 201 `CatalogSource` |
| `POST /api/admin/pack-catalog/sources/archive?name=&label=&packs_path=&replace_builtin=` | архив целиком (`application/octet-stream`) | 201 `CatalogSource` |
| `PUT /api/admin/pack-catalog/sources/{id}/archive?name=` | архив целиком | `CatalogSource` |
| `PATCH /api/admin/pack-catalog/sources/{id}` | `UpdateSourceRequest` | `CatalogSource` |
| `DELETE /api/admin/pack-catalog/sources/{id}` | | 204 |
| `POST /api/admin/pack-catalog/sources/{id}/check` | | `CatalogCheck` |
| `POST /api/admin/pack-catalog/sources/{id}/apply` | `ApplySourceRequest` | `CatalogApply` |
| `GET /api/admin/pack-catalog/sources/{id}/history` | | `CatalogEventList` |
| `GET /api/v1/pack-studio/workspaces/{id}/catalog` | | `WorkspaceCatalog` (локально) |
| `POST /api/v1/pack-studio/workspaces/{id}/catalog/check` | `WorkspaceCatalogCheckRequest` | `CatalogCheck` |
| `POST /api/v1/pack-studio/workspaces/{id}/catalog/apply` | `ApplySourceRequest` | `CatalogApply` |
| `PATCH /api/v1/pack-studio/workspaces/{id}/catalog` | `UpdateSourceRequest` (только `enabled`) | `WorkspaceCatalog` |
| `DELETE /api/v1/pack-studio/workspaces/{id}/catalog` | | 204 |

`GET /api/v1/catalog/packs` (мастер проекта) отдаёт у пака `origin` (`builtin` или `subscribed` с меткой,
адресом, ref и ревизией источника) и не показывает паки выключенных источников и скрытые версии.

## Правила

- «Применить» берёт только проверенную ревизию (`revision` из `CatalogCheck`); источник изменился после проверки:
  `revision_moved`. План сверяется со свежим каталогом под замком хранилища.
- В каталог попадают только выпущенные версии (есть в `releases.yaml` источника), каталог которых совпал с
  дайджестом реестра. `verdict`: `new` появится, `present` уже есть, `changed` тот же номер с другим дайджестом
  (отказ «версия изменена в источнике»), `incompatible` не для этой Студии (`min_studio`, `manifest_format`),
  `invalid` ошибки линтера или каталог изменён после выпуска, `unreleased` нет в реестре.
- Пак с id вшитого пака подключается только с `replace_builtin`; пак другого источника: `conflict: other_source`.
- Хранилище только дополняется: выключение и удаление источника прячут его паки из мастера, версии остаются для
  проектов.
