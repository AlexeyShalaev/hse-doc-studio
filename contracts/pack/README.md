# Схемы пака

JSON Schema (draft 2020-12) манифестов пака (`docs/design/template-studio.md`, D12). По ним Студия шаблонов строит формы и подсказки, по ним же проверяется пак до отправки.

| Файл | Что описывает |
|---|---|
| `version.schema.json` | `templates/<шаблон>/versions/<версия>/version.yaml`: документы, поля, анкеты, подписи (места на якорях `placements`, метки даты `default_dates`, `anchor_macros`), профили сдачи (`signing_route`, `signing_slots`, `deadline_hint`) |
| `doc.schema.json` | `files/<документ>/doc.yaml`; та же запись с обязательным `id` в `documents` манифеста старого вида |
| `template.schema.json` | `templates/<шаблон>/template.yaml` |
| `releases.schema.json` | `templates/<шаблон>/releases.yaml` |
| `pack.schema.json` | `pack.yaml` |
| `common.schema.json` | общие определения: локализованные строки, id, места и метки даты |

Правила проверок `checks/*.yaml` схемы пока не имеют.

YAML-даты (`released_at: 2026-11-14`) перед проверкой приводятся к строке ISO.

## Схема и лоадер

- Схема строже лоадера. Лоадер (`infra/template/yaml_template_repository.py`) терпит незнакомое и отбрасывает битый элемент, чтобы пак от более новой Студии открывался. Схема описывает, как писать пак: незнакомый ключ в ней ошибка.
- Что схема допускает, лоадер разбирает целиком. Правила, которых JSON Schema не выражает, названы в `description`: рамка внутри листа A4 (`x_mm + width_mm`), подсказка срока без конкретных дат.
- `manifest_format` не выше `MANIFEST_FORMAT` Студии.

Проверки в `services/api/tests/unit/contract/`:

- `test_pack_schemas.py`: схемы корректны, все паки репозитория их проходят, каждый ключ, который читает лоадер, описан в схеме. Известные дефекты выпущенных версий перечислены в тесте поимённо;
- `test_pack_schema_loader.py`: выборка образцов по самим схемам (hypothesis) проходит лоадер без потерь.

Форму меняют так: сначала схема, затем лоадер, линтер пака и справка `docs/*/reference/pack.md`, тесты в том же коммите.

Копия схем лежит в пакете (`services/api/hse_doc_studio/infra/pack_studio/schemas/`): по ней `hse-doc-studio pack check` проверяет паки в образе. После правки схемы скопируйте её туда; совпадение сверяет `test_pack_schemas_copy.py`.
