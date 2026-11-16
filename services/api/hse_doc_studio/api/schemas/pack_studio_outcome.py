"""Схемы вычислителя результата Студии шаблонов (`docs/design/template-studio-outcome.md`, раздел 4).

Контракт «результат в центре»: по версии шаблона и вводным (язык, вид работы, состав, руководители, NDA, поля, ответы
анкет, варианты документов) сервер считает результат (документы, поля, участники, точки сдачи, маршрут, проверки) и
объясняет каждое решение цепочкой правил (`trace`). Клиент условий не считает: он показывает то, что вернул сервер.

Эталоны лежат в `contracts/pack-studio/fixtures`, тест `tests/unit/contract/test_pack_studio_contract.py` сверяет их
с этими моделями, а клиентские схемы zod (`entities/pack-studio/api/outcome.ts`) разбирают те же эталоны. Эндпоинты
`outcome/inputs` и `outcome` работают (срез O2, `api/routers/v1/pack_studio_outcome.py`, служба
`use_cases/pack_studio/outcome_service.py`), так же сценарии: список, запись, удаление и прогон (срез O6,
`api/routers/v1/pack_studio_scenarios.py`, служба `use_cases/pack_studio/scenario_service.py`); остальные приходят со
своими срезами плана (раздел 7). Ядро расчёта (срез O1) в `core/pack_studio/outcome` и `use_cases/pack_studio/outcome`.

Все значения вводных строки, как в комбинации предпросмотра (`yes` и `no` у логических), чтобы состояние можно было
положить в адрес страницы.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.api.schemas.pack_studio import PackPreviewExample
from hse_doc_studio.api.schemas.pack_studio_submission import PackDocSlotRef, PackRoutePerson, PackSubmissionWhen

Localized = dict[str, str]

# Откуда считать: рабочее дерево (с несохранёнными правками), последний коммит ветки, вершина базовой ветки.
OutcomeStateName = Literal["work_tree", "head", "base"]
# Разделы результата: колонки матрицы, строки сводки диффа, адресат правила.
SectionName = Literal["documents", "meta", "forms", "participants", "points", "route", "checks"]
DocumentStateName = Literal["active", "inactive", "absent"]
LangStateName = Literal["native", "fallback"]
ScopeName = Literal["shared", "personal"]
MetaScopeName = Literal["project", "author"]
MetaTypeName = Literal["string", "bool", "person", "select", "font"]
RequiredAtName = Literal["create", "finalize", "never"]
RoleName = Literal["author", "supervisor", "co_supervisor", "academic_supervisor"]
OrgName = Literal["university", "company"]
CheckSeverityName = Literal["info", "warn", "err"]
FindingSeverityName = Literal["error", "warning", "info"]
OrderSourceName = Literal["profile", "version", "builtin"]
ItemOffReason = Literal["nda", "kind", "absent", "inactive"]
CheckOffReason = Literal["disabled", "category_disabled", "no_active_document"]
InputGroupName = Literal["project", "people", "meta", "answers", "variants"]
# Что в результате не считается мгновенно и в этом ответе не участвует (раздел 8): правила проверок на Python,
# места подписей по якорям собранного PDF, содержимое TeX и Jinja.
OutOfScopeName = Literal["python_checks", "signature_anchors", "tex_content", "jinja_content"]
IncludeName = Literal["branches", "checks"]

# Происхождение и вид правила, предикат, роль и исход решения (раздел 4.3).
RuleOriginName = Literal["manifest", "builtin"]
BuiltinRuleName = Literal["nda_gate", "manuals_gate", "presentation_variant", "builtin_route"]
RuleKindName = Literal[
    "supported_kinds",
    "supported_staffing",
    "supported_langs",
    "document_scope",
    "variant_langs",
    "builtin_gate",
    "field_kinds",
    "visible_if",
    "required_at",
    "form_kinds",
    "form_per_author",
    "item_kinds",
    "extra_kinds",
    "skip_if_nda",
    "item_document",
    "slot_when",
    "slot_optional",
    "route_order",
    "check_applies",
    "check_disabled",
]
PredicateOpName = Literal["in", "equals", "contains_any", "present", "truthy"]
EffectName = Literal["gate", "exclude", "add", "order", "display", "require"]
JoinName = Literal["all", "any"]
VerdictName = Literal["held", "not_held", "skipped"]

# Изменения: `+` появилось, `~` изменилось, `-` исчезло (раздел 3.7).
ChangeSymbol = Literal["+", "~", "-"]
ChangeSubjectName = Literal[
    "document",
    "variant",
    "meta_field",
    "form",
    "form_field",
    "participant",
    "point",
    "item",
    "extra_item",
    "route_step",
    "route_pair",
    "skipped_pair",
    "check_rule",
]

_ID = 128
_TEXT = 2000
_MAX_INPUTS = 64


class OutcomeElementRef(StrictModel):
    """Элемент результата: раздел и id (у вложенных через косую черту: `final/report/supervisor`)."""

    section: SectionName
    id: str = Field(min_length=1, max_length=_TEXT)


# ── Правила и объяснения ─────────────────────────────────────────────────────


class OutcomeRuleRef(StrictModel):
    """Где лежит правило: `manifest` это файл от каталога версии и путь JSON Pointer внутри него (по нему форма
    открывается на нужной записи); `builtin` это правило, зашитое в движок (NDA, руководства, вариант презентации)."""

    origin: RuleOriginName
    file: str | None
    pointer: str | None
    builtin: BuiltinRuleName | None

    @model_validator(mode="after")
    def _origin(self) -> OutcomeRuleRef:
        if self.origin == "manifest" and (self.file is None or self.pointer is None):
            raise ValueError("a manifest rule needs file and pointer")
        if self.origin == "builtin" and self.builtin is None:
            raise ValueError("a builtin rule needs builtin")
        return self


class OutcomeTerm(StrictModel):
    """Одно условие закрытого языка: `in` (значение входит в `expected`), `equals`, `contains_any` (строка содержит
    одну из подстрок), `present` (человек или поле есть), `truthy` (логическая вводная включена)."""

    op: PredicateOpName
    subject: str = Field(min_length=1, max_length=_ID)
    expected: list[str] = Field(max_length=32)


class OutcomeTrace(StrictModel):
    """Одно решение вычислителя: правило, условие, фактические значения и исход.

    `status`: `held` условие выполнено, `not_held` не выполнено, `skipped` не проверялось (исход уже решён раньше).
    `effect` говорит, что правило делает с элементом: `gate` (элемент есть, только если условие выполнено),
    `exclude` (при выполнении элемент убирается), `add` (при выполнении добавляется), `order` (задаёт порядок),
    `display` (видимость), `require` (обязательность)."""

    id: str = Field(min_length=1, max_length=32)
    rule: OutcomeRuleRef
    kind: RuleKindName
    effect: EffectName
    join: JoinName
    terms: list[OutcomeTerm] = Field(max_length=8)
    # Что вычислитель увидел: вводная или факт (`supervisor.role`) и его значение.
    actual: dict[str, str] = Field(max_length=16)
    status: VerdictName
    # Элементы результата, о которых это решение (обратная ссылка на `why`).
    subjects: list[OutcomeElementRef] = Field(max_length=64)


# ── Результат ────────────────────────────────────────────────────────────────


class OutcomeVariantOption(StrictModel):
    id: str
    label: Localized
    # Языки проекта, в которых вариант доступен; пусто: во всех.
    langs: list[str]
    # Доступен при языке проекта этого результата.
    available: bool
    chosen: bool
    why: list[str]


class OutcomeInstance(StrictModel):
    """Экземпляр документа в проекте: у личных документов команды по одному на автора."""

    id: str
    owner: str | None
    owner_name: str | None
    # Итоговое имя файла для языка проекта; null: имя задаёт шаблон при сборке.
    file_name: str | None


class OutcomeDocument(StrictModel):
    """Документ ростера. `state`: `active` в комплекте, `inactive` в проекте, но выключен (NDA, руководства),
    `absent` в проекте этого вида работы или состава нет. `lang_state`: `fallback` у языка проекта нет редакции,
    берётся язык шаблона по умолчанию."""

    id: str
    name: Localized
    group: str | None
    scope: ScopeName
    required: bool
    state: DocumentStateName
    lang_state: LangStateName
    languages: list[str]
    variants: list[OutcomeVariantOption]
    instances: list[OutcomeInstance]
    # Исходник выбранного варианта и языка от каталога версии; null: документа нет.
    source_file: str | None
    # `doc.yaml` документа, куда ведёт «Правка правила».
    manifest: str
    why: list[str]


class OutcomeMetaField(StrictModel):
    id: str
    type: MetaTypeName
    label: Localized
    scope: MetaScopeName
    group: str | None
    visible: bool
    required_at: RequiredAtName
    # Значение в синтетическом проекте результата (из набора данных и умолчаний); null: пусто.
    value: str | None
    options: list[str]
    why: list[str]


class OutcomeFormField(StrictModel):
    id: str
    type: str
    label: Localized
    visible: bool
    required: bool
    why: list[str]


class OutcomeForm(StrictModel):
    id: str
    title: Localized
    per_author: bool
    # Анкета есть в проекте этого вида работы.
    applies: bool
    required_for_pack: bool
    fields: list[OutcomeFormField]
    why: list[str]


class OutcomeParticipant(StrictModel):
    """Ожидаемый участник: автор или руководитель. `present` ложно у руководителя, которого нет в комбинации
    (слот остаётся виден бледным)."""

    persona: str
    role: RoleName
    name: str
    present: bool
    org: OrgName | None
    why: list[str]


class OutcomePointItem(StrictModel):
    doc_id: str
    active: bool
    off_reason: ItemOffReason | None
    signatures: list[str]
    why: list[str]


class OutcomePointExtra(StrictModel):
    source: str
    output_name: str
    format: str | None
    active: bool
    off_reason: ItemOffReason | None
    why: list[str]


class OutcomeRoutePair(StrictModel):
    doc_id: str
    slot_id: str
    persona: str
    source: Literal["point", "preset"]
    optional: bool
    when: PackSubmissionWhen | None
    why: list[str]


class OutcomeSkippedPair(StrictModel):
    doc_id: str
    slot_id: str
    when: PackSubmissionWhen | None
    why: list[str]


class OutcomeRoute(StrictModel):
    """Маршрут подписания точки тем же кодом, что маршрут проекта. `steps` пусто: подписи точке не нужны."""

    steps: list[list[PackRoutePerson]]
    pairs: list[OutcomeRoutePair]
    skipped: list[OutcomeSkippedPair]
    # Подписи, которые автор проекта включит сам.
    may_add: list[PackDocSlotRef]
    order_source: OrderSourceName
    preset: bool
    why: list[str]


class OutcomePoint(StrictModel):
    """Точка сдачи (профиль `pack_submission.profiles`); `index` это индекс профиля в списке YAML."""

    id: str
    index: int
    name: Localized
    deadline_hint: Localized | None
    items: list[OutcomePointItem]
    extra_items: list[OutcomePointExtra]
    route: OutcomeRoute
    why: list[str]


class OutcomeCheckRule(StrictModel):
    """Правило проверок в этом результате. `applies_to` это активные документы, к которым оно применяется;
    результат прогона не считается (раздел 8), считается только применимость."""

    id: str
    title: Localized
    category: str | None
    severity: CheckSeverityName
    engine: str
    enabled: bool
    off_reason: CheckOffReason | None
    applies_to: list[str]
    why: list[str]


class OutcomeSectionDelta(StrictModel):
    section: SectionName
    added: int = Field(ge=0)
    changed: int = Field(ge=0)
    removed: int = Field(ge=0)


class OutcomeAlternative(StrictModel):
    value: str
    label: Localized | None
    fingerprint: str
    # Что изменится в результате, если выбрать это значение; пусто у текущего.
    delta: list[OutcomeSectionDelta]


class OutcomeBranch(StrictModel):
    """Ветка результата: вводная, от которой зависит результат, и что будет при каждом другом значении."""

    input: str
    label: Localized | None
    chosen: str
    affects: list[SectionName]
    alternatives: list[OutcomeAlternative]


class OutcomeSectionPrint(StrictModel):
    section: SectionName
    fingerprint: str
    # Сколько элементов раздела в результате (документов в комплекте, участников, пунктов); для матрицы.
    count: int = Field(ge=0)


class OutcomeDigestPoint(StrictModel):
    id: str
    # Активные документы точки.
    items: list[str]
    # Шаги маршрута персонами.
    steps: list[list[str]]
    pairs: int = Field(ge=0)


class OutcomeDigest(StrictModel):
    """Сжатый результат: хватает, чтобы мгновенно перерисовать экран из атласа, сравнить сценарии и записать
    снимок ожидаемого результата в сценарий."""

    documents: dict[str, DocumentStateName]
    participants: list[str]
    meta_visible: list[str]
    points: list[OutcomeDigestPoint]
    sections: list[OutcomeSectionPrint]


# ── Запрос и ответ вычислителя ───────────────────────────────────────────────


class PackOutcomeRequest(StrictModel):
    """`inputs` поверх набора данных (`example`) и значений по умолчанию; вводные сценария (`scenario`) лежат
    между ними: сначала умолчания, затем сценарий, затем `inputs`. Незнакомая вводная или значение вне списка:
    `inputs_invalid`."""

    state: OutcomeStateName = "work_tree"
    scenario: str | None = Field(default=None, max_length=_ID)
    example: str | None = Field(default=None, max_length=255)
    inputs: dict[str, str] = Field(default_factory=dict, max_length=_MAX_INPUTS)
    # Дорогие части ответа: ветки (что-если по каждой вводной), правила проверок.
    include: list[IncludeName] = Field(default_factory=list, max_length=2)


class PackOutcomeResponse(StrictModel):
    workspace_id: str
    pack: str
    template: str
    version: str
    state: OutcomeStateName
    # Дайджест манифестов, по которым считали: кэш и устаревание ответа.
    revision: str
    # Полные вводные после умолчаний и сценария.
    inputs: dict[str, str]
    example: str
    # Отпечаток структуры результата без `trace`: одинаков у одинаковых результатов.
    fingerprint: str
    documents: list[OutcomeDocument]
    meta: list[OutcomeMetaField]
    forms: list[OutcomeForm]
    participants: list[OutcomeParticipant]
    points: list[OutcomePoint]
    # null: части не просили (`include`).
    checks: list[OutcomeCheckRule] | None
    branches: list[OutcomeBranch] | None
    digest: OutcomeDigest
    trace: list[OutcomeTrace]
    out_of_scope: list[OutOfScopeName]
    elapsed_ms: int = Field(ge=0)


# ── Вводные версии ───────────────────────────────────────────────────────────


class OutcomeInputValue(StrictModel):
    value: str
    label: Localized | None


class OutcomeInput(StrictModel):
    """Вводная панели: строится из схемы версии (язык версии, виды работы документов, составы, поля select и bool,
    поля анкет в `visible_if`, варианты документов). Идентификаторы: `lang`, `kind`, `staffing`, `supervisor`,
    `co_supervisor`, `academic_supervisor`, `nda`, `meta.<поле>`, `answer.<анкета>.<поле>`, `variant.<документ>`."""

    id: str
    group: InputGroupName
    type: Literal["select", "bool"]
    label: Localized | None
    values: list[OutcomeInputValue]
    default: str
    # Разделы, которые меняются при смене этой вводной (по атласу), и число правил манифеста, которые её читают.
    affects: list[SectionName]
    rules: int = Field(ge=0)


class PackOutcomeInputsResponse(StrictModel):
    workspace_id: str
    pack: str
    template: str
    version: str
    state: OutcomeStateName
    revision: str
    inputs: list[OutcomeInput]
    examples: list[PackPreviewExample]
    default_example: str
    defaults: dict[str, str]


# ── Атлас ────────────────────────────────────────────────────────────────────


class AtlasDimension(StrictModel):
    """Измерение атласа: вводная, которая меняет хотя бы один раздел результата."""

    input: str
    values: list[str]
    default: str
    affects: list[SectionName]
    rules: list[OutcomeRuleRef] = Field(max_length=32)


class AtlasIgnored(StrictModel):
    """Вводная вне таблицы: `no_effect` ничего не меняет, `cosmetic` меняет только имена файлов, доступность
    вариантов и языковую редакцию документа (точный результат даёт расчёт, атлас этого не хранит)."""

    input: str
    reason: Literal["no_effect", "cosmetic"]


class AtlasOutcome(StrictModel):
    id: str
    fingerprint: str
    digest: OutcomeDigest
    # Сколько строк таблицы дают этот исход.
    rows: int = Field(ge=1)


class AtlasRow(StrictModel):
    """Строка таблицы: `key` это значения измерений по порядку `dimensions` через `|` (в значении `|` пишется
    `%7C`), `outcome` это id исхода."""

    key: str
    outcome: str


class PackOutcomeAtlasResponse(StrictModel):
    workspace_id: str
    pack: str
    template: str
    version: str
    state: OutcomeStateName
    revision: str
    dimensions: list[AtlasDimension]
    # Вводные вне таблицы: панель показывает их приглушёнными («ничего не меняет» или «только имена файлов»).
    ignored: list[AtlasIgnored]
    # Размер полного перебора всех вводных и таблица после отбрасывания неважных.
    combinations_total: int = Field(ge=1)
    rows_total: int = Field(ge=1)
    outcomes_distinct: int = Field(ge=1)
    outcomes: list[AtlasOutcome]
    rows: list[AtlasRow]
    elapsed_ms: int = Field(ge=0)


# ── Сценарии ─────────────────────────────────────────────────────────────────


class DocumentStateAssertion(StrictModel):
    kind: Literal["document_state"]
    doc: str = Field(min_length=1, max_length=_ID)
    state: DocumentStateName


class DocumentCountAssertion(StrictModel):
    kind: Literal["document_count"]
    state: DocumentStateName
    count: int = Field(ge=0, le=1000)


class MetaVisibleAssertion(StrictModel):
    kind: Literal["meta_visible"]
    field: str = Field(min_length=1, max_length=_ID)
    visible: bool


class ParticipantAssertion(StrictModel):
    kind: Literal["participant_present"]
    persona: str = Field(min_length=1, max_length=_ID)
    present: bool


class ItemActiveAssertion(StrictModel):
    kind: Literal["item_active"]
    point: str = Field(min_length=1, max_length=_ID)
    doc: str = Field(min_length=1, max_length=_ID)
    active: bool


class RouteStepsAssertion(StrictModel):
    kind: Literal["route_steps"]
    point: str = Field(min_length=1, max_length=_ID)
    # Персоны по шагам; внутри шага порядок не важен.
    steps: list[list[str]] = Field(max_length=16)


class RoutePairAssertion(StrictModel):
    kind: Literal["route_pair"]
    point: str = Field(min_length=1, max_length=_ID)
    doc: str = Field(min_length=1, max_length=_ID)
    slot: str = Field(min_length=1, max_length=_ID)
    persona: str = Field(min_length=1, max_length=_ID)
    present: bool


ScenarioAssertion = Annotated[
    DocumentStateAssertion
    | DocumentCountAssertion
    | MetaVisibleAssertion
    | ParticipantAssertion
    | ItemActiveAssertion
    | RouteStepsAssertion
    | RoutePairAssertion,
    Field(discriminator="kind"),
]


class PackScenario(StrictModel):
    """Файл сценария `<пак>/templates/<шаблон>/scenarios/<id>.yaml` (рядом с `examples/`, вне каталога версии:
    дайджест выпущенной версии не меняется). `inputs` частичные, остальное по умолчанию. Ожидание: `snapshot`
    (снимок результата, записывается кнопкой) и (или) `assertions`; без обоих сценарий только показывает результат.
    `versions` это шаблоны номеров (`2026.1.*`); пусто: сценарий проверяется на любой версии."""

    format: Literal[1]
    name: Localized = Field(min_length=1, max_length=4)
    description: Localized = Field(default_factory=dict, max_length=4)
    example: str | None = Field(default=None, max_length=255)
    inputs: dict[str, str] = Field(max_length=_MAX_INPUTS)
    versions: list[str] = Field(default_factory=list, max_length=16)
    snapshot: OutcomeDigest | None = None
    assertions: list[ScenarioAssertion] = Field(default_factory=list, max_length=64)


class PackScenarioEntry(StrictModel):
    """Сценарий в списке: файл, ETag и разобранное содержимое; `scenario` null у файла, который не разобран
    (`error` почему), он виден в списке и чинится в «Исходнике»."""

    id: str
    path: str
    etag: str
    scenario: PackScenario | None
    error: str | None


class PackScenarioListResponse(StrictModel):
    workspace_id: str
    pack: str
    template: str
    # Папка сценариев от папки паков.
    dir: str
    scenarios: list[PackScenarioEntry]


class PackScenarioWriteRequest(StrictModel):
    """Запись сценария (`PUT .../scenarios/{id}` с `If-Match`): сервер пишет канонический YAML. `record_snapshot`
    заменяет `snapshot` текущим результатом сценария на выбранном состоянии."""

    scenario: PackScenario
    record_snapshot: OutcomeStateName | None = None
    # Версия, на которой считается снимок; null: старшая версия шаблона на диске, подходящая под `versions` сценария.
    version: str | None = Field(default=None, max_length=_ID)


# ── Покрытие и находки линтера результата ────────────────────────────────────


class RuleCoverage(StrictModel):
    rule: OutcomeRuleRef
    kind: RuleKindName
    # Какие исходы правила видели сценарии: `held` и `not_held`; покрыто полностью, когда видели оба.
    seen: list[Literal["held", "not_held"]]
    scenarios: list[str]


class OutcomeCoverage(StrictModel):
    scenarios: int = Field(ge=0)
    rules_total: int = Field(ge=0)
    rules_covered: int = Field(ge=0)
    rules_half: int = Field(ge=0)
    rules_uncovered: int = Field(ge=0)
    rules: list[RuleCoverage]


class PackScenarioRunRequest(StrictModel):
    state: OutcomeStateName = "work_tree"
    # null: все сценарии шаблона.
    scenarios: list[str] | None = Field(default=None, max_length=200)
    # Версия, на которой идёт прогон; null: старшая версия шаблона на диске. Сценарий вне своих `versions` на ней
    # не выполняется (`unchecked` с пояснением в `message`).
    version: str | None = Field(default=None, max_length=_ID)


class OutcomeChange(StrictModel):
    """Одно изменение результата: `symbol`, раздел, вид и id элемента, подпись для человека и значения «было» и
    «стало» (null у появившегося и исчезнувшего)."""

    symbol: ChangeSymbol
    section: SectionName
    kind: ChangeSubjectName
    id: str = Field(min_length=1, max_length=_TEXT)
    label: str = Field(max_length=_TEXT)
    before: str | None
    after: str | None


class ScenarioFailure(StrictModel):
    # Индекс утверждения; null: расхождение со снимком (подробности в `changes`).
    index: int | None
    kind: str
    expected: str
    actual: str
    why: list[str]


ScenarioStatusName = Literal["passed", "failed", "error", "unchecked"]


class PackScenarioRunResult(StrictModel):
    """`unchecked`: у сценария нет ни снимка, ни утверждений. `error`: вводные не подходят к версии
    (`message`), результата нет."""

    scenario: str
    status: ScenarioStatusName
    fingerprint: str | None
    failures: list[ScenarioFailure]
    # Расхождение со снимком в виде изменений «снимок -> сейчас».
    changes: list[OutcomeChange]
    message: str | None


class PackScenarioRunResponse(StrictModel):
    workspace_id: str
    pack: str
    template: str
    version: str
    state: OutcomeStateName
    revision: str
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: int = Field(ge=0)
    unchecked: int = Field(ge=0)
    results: list[PackScenarioRunResult]
    # Покрытие правил манифеста этими сценариями (раздел 6.2).
    coverage: OutcomeCoverage


class OutcomeFinding(StrictModel):
    """Находка линтера результата (раздел 6.1). `witnesses` это до трёх вводных, на которых она видна;
    `elements` это затронутые элементы; `line` с единицы, если файл удалось разобрать."""

    rule_id: str = Field(min_length=1, max_length=64)
    severity: FindingSeverityName
    message: str
    file: str | None
    pointer: str | None
    line: int | None
    elements: list[OutcomeElementRef] = Field(max_length=16)
    witnesses: list[dict[str, str]] = Field(max_length=3)


class PackOutcomeLintResponse(StrictModel):
    workspace_id: str
    pack: str
    template: str
    version: str
    state: OutcomeStateName
    revision: str
    errors: int = Field(ge=0)
    warnings: int = Field(ge=0)
    findings: list[OutcomeFinding]
    coverage: OutcomeCoverage


# ── Сравнения: два сценария, «до и после», матрица ───────────────────────────


class OutcomeSubject(StrictModel):
    """Одна сторона сравнения: сценарий и (или) вводные на выбранном состоянии версии."""

    state: OutcomeStateName = "work_tree"
    scenario: str | None = Field(default=None, max_length=_ID)
    example: str | None = Field(default=None, max_length=255)
    inputs: dict[str, str] = Field(default_factory=dict, max_length=_MAX_INPUTS)


class OutcomeSide(StrictModel):
    state: OutcomeStateName
    revision: str
    fingerprint: str
    inputs: dict[str, str]


class PackOutcomeCompareRequest(StrictModel):
    left: OutcomeSubject
    right: OutcomeSubject


class PackOutcomeCompareResponse(StrictModel):
    workspace_id: str
    pack: str
    template: str
    version: str
    left: OutcomeSide
    right: OutcomeSide
    identical: bool
    summary: list[OutcomeSectionDelta]
    changes: list[OutcomeChange]


class PackOutcomeImpactRequest(StrictModel):
    """«До и после»: рабочее дерево против базы (`base`: вершина базовой ветки, `head`: последний коммит ветки)
    по сценариям шаблона и по атласу."""

    base: Literal["base", "head"] = "base"
    scenarios: list[str] | None = Field(default=None, max_length=200)
    include_atlas: bool = True


class ImpactScenario(StrictModel):
    scenario: str
    name: Localized
    status: Literal["unchanged", "changed", "error"]
    changes: list[OutcomeChange]
    message: str | None


class ImpactAtlas(StrictModel):
    rows_total: int = Field(ge=0)
    rows_changed: int = Field(ge=0)
    outcomes_before: int = Field(ge=0)
    outcomes_after: int = Field(ge=0)


class ImpactSummary(StrictModel):
    scenarios_total: int = Field(ge=0)
    scenarios_changed: int = Field(ge=0)
    scenarios_unchanged: int = Field(ge=0)
    scenarios_error: int = Field(ge=0)
    sections: list[OutcomeSectionDelta]
    atlas: ImpactAtlas | None


class PackOutcomeImpactResponse(StrictModel):
    workspace_id: str
    pack: str
    template: str
    version: str
    base: Literal["base", "head"]
    base_revision: str
    work_tree_revision: str
    summary: ImpactSummary
    scenarios: list[ImpactScenario]
    # Находки линтера результата, которых на базе не было: «предложение изменений» их показывает.
    new_findings: list[OutcomeFinding]


class PackOutcomeMatrixRequest(StrictModel):
    state: OutcomeStateName = "work_tree"
    scenarios: list[str] | None = Field(default=None, max_length=200)
    # `base`: у каждой клетки пометка, изменилась ли она против вершины базовой ветки.
    against: Literal["base"] | None = None


class MatrixCell(StrictModel):
    section: SectionName
    fingerprint: str
    count: int = Field(ge=0)
    # null: сравнения с базой не просили или сценария на базе нет.
    changed: bool | None


class MatrixRow(StrictModel):
    scenario: str
    name: Localized
    inputs: dict[str, str]
    cells: list[MatrixCell]


class PackOutcomeMatrixResponse(StrictModel):
    workspace_id: str
    pack: str
    template: str
    version: str
    state: OutcomeStateName
    revision: str
    columns: list[SectionName]
    rows: list[MatrixRow]


# ── «Почему?» ────────────────────────────────────────────────────────────────


class PackOutcomeExplainRequest(StrictModel):
    state: OutcomeStateName = "work_tree"
    scenario: str | None = Field(default=None, max_length=_ID)
    example: str | None = Field(default=None, max_length=255)
    inputs: dict[str, str] = Field(default_factory=dict, max_length=_MAX_INPUTS)
    element: OutcomeElementRef


class OutcomeCounterfactual(StrictModel):
    """Что станет с элементом, если одну вводную поставить в другое значение."""

    input: str
    value: str
    # Состояние элемента при этом: у документа `active`, `inactive` или `absent`, у остальных `present` или `absent`.
    result: str


class PackOutcomeExplainResponse(StrictModel):
    element: OutcomeElementRef
    state: str
    # Цепочка решений от первого правила к последнему.
    chain: list[OutcomeTrace]
    # Другие элементы, на которые влияют те же правила («это правило решает судьбу ещё N элементов»).
    readers: list[OutcomeElementRef] = Field(max_length=64)
    counterfactuals: list[OutcomeCounterfactual] = Field(max_length=32)
