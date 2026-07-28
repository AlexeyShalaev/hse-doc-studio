import { type ChangeEvent, useCallback, useMemo, useState } from "react";
import {
  AlertTriangle,
  ChevronsDownUp,
  ChevronsUpDown,
  Play,
  RefreshCw,
  Search,
  Square,
  X,
} from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { getDocMeta, useDocuments } from "@entities/document";
import type { DocMeta } from "@entities/document";
import {
  useCancelProjectCompiles,
  useCompileStreamStore,
  useIsProjectStalled,
  useStartCompileAll,
} from "@entities/compile";
import { useForms } from "@entities/form";
import { useProject } from "@entities/project";
import { Spinner } from "@shared/ui/Spinner";
import { NowBlock } from "./NowBlock";
import { DocSection } from "./DocSection";
import type { DocSectionRow } from "./DocSection";
import { buildDocSections } from "./lib/buildDocSections";
import type { DocumentItem } from "./lib/buildDocSections";

export type DocumentsPanelProps = {
  projectId: string;
  selectedDocId?: string | undefined;
  onSelectDoc: (docId: string) => void;
  /**
   * Открыть анкету. Нужен блоку «Сейчас»: незаполненная обязательная анкета —
   * такой же блокер сдачи, как упавшая сборка, и вести к ней надо отсюда, хотя
   * сами анкеты живут в панели «Сдача».
   */
  onOpenForm?: ((formId: string) => void) | undefined;
  /**
   * Анкеты, входящие в пакет БЛИЖАЙШЕЙ точки (CheckpointReadiness.formIds).
   * Блок «Сейчас» отвечает на вопрос «за что взяться прямо сейчас», а анкета
   * относится к конкретной точке: «Декларация ИИ» нужна только к ПДП и ГИА, и
   * до них это неснимаемый ложный блокер, занимающий одну из трёх строк. Не
   * задано (точки ещё не загружены) — анкет в блоке нет вовсе: промолчать
   * честнее, чем звать заполнять несрочное.
   */
  activeFormIds?: readonly string[] | undefined;
  /**
   * Ближайшая (или закреплённая) контрольная точка. Даёт панели чип «Для КТ…»,
   * который сужает список до состава этой точки, и кольцо готовности в подвале.
   * Считает страница — здесь только отображение.
   */
  checkpoint?:
    | {
        name: string;
        /** id документов, входящих в точку; пусто — состав не описан. */
        docIds: ReadonlySet<string>;
        done: number;
        total: number;
        isUnknown: boolean;
      }
    | undefined;
};

/** Статусный чип: активен ровно один. */
type StatusChip = "all" | "errors" | "notBuilt" | "checkpoint";

// Всё состояние панели в одном объекте вместе с проектом, для которого оно
// прочитано, — так переключение проекта обходится без эффекта-сбрасывателя.
type PanelState = {
  projectId: string;
  query: string;
  statusChip: StatusChip;
  authorKeys: string[];
  collapsedKeys: string[];
};

const collapsedStorageKey = (projectId: string): string =>
  `hse-studio.nav.collapsed.${projectId}`;
const authorsStorageKey = (projectId: string): string =>
  `hse-studio.nav.authors.${projectId}`;

const readStoredKeys = (storageKey: string): string[] => {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (raw == null) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((value): value is string => typeof value === "string");
  } catch {
    // Приватный режим / битое значение — просто стартуем с пустого набора.
    return [];
  }
};

const writeStoredKeys = (storageKey: string, keys: string[]): void => {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(keys));
  } catch {
    // Память о свёрнутых группах — не та вещь, ради которой падают.
  }
};

const initialPanelState = (projectId: string): PanelState => ({
  projectId,
  query: "",
  statusChip: "all",
  authorKeys: readStoredKeys(authorsStorageKey(projectId)),
  collapsedKeys: readStoredKeys(collapsedStorageKey(projectId)),
});

const matchesStatus = (doc: DocumentItem, chip: StatusChip): boolean => {
  if (chip === "errors") return doc.status === "err";
  if (chip === "notBuilt") return doc.status === "draft";
  return true;
};

// Фильтр идёт по коду И названию: студент ищет и «ТЗ», и «Техническое
// задание», и «Иванов» (ФИО попадает в название личного документа).
const matchesQuery = (meta: DocMeta, needle: string): boolean =>
  needle === "" ||
  meta.code.toLowerCase().includes(needle) ||
  meta.name.toLowerCase().includes(needle);

export const DocumentsPanel = ({
  projectId,
  selectedDocId,
  onSelectDoc,
  onOpenForm,
  activeFormIds,
}: DocumentsPanelProps) => {
  const { t } = useTranslation("workbench");
  const { data: project } = useProject(projectId);
  const { data: documents, isLoading } = useDocuments(projectId);
  const { startAll, isRunning: isCompiling } = useStartCompileAll(projectId);
  const { cancelAll } = useCancelProjectCompiles(projectId);
  const isStalled = useIsProjectStalled(projectId);
  const compileStreams = useCompileStreamStore((s) => s.streams);

  const [storedState, setState] = useState<PanelState>(() =>
    initialPanelState(projectId),
  );
  // Панель одна на все проекты, а память о свёрнутых группах и выбранных
  // авторах — своя у каждого. Состояние помнит, для какого проекта оно
  // прочитано, и при переключении пересобирается прямо в рендере: useEffect
  // с setState дал бы лишний каскадный рендер на каждом переходе.
  const panelState = useMemo(
    () =>
      storedState.projectId === projectId
        ? storedState
        : initialPanelState(projectId),
    [storedState, projectId],
  );
  const { query, statusChip, authorKeys, collapsedKeys } = panelState;

  const isDocBuilding = useCallback(
    (docId: string): boolean =>
      compileStreams[`${projectId}::${docId}`]?.status === "running",
    [compileStreams, projectId],
  );

  const docs = documents ?? [];
  const { data: formsData } = useForms(projectId);
  // Только анкеты ближайшей точки — тот же отбор, что дал кольцо её готовности,
  // поэтому «Сейчас» больше не может звать заполнять то, чего эта точка не
  // требует. Заодно отсекает личные анкеты соавторов: снять их студент всё
  // равно не может, а места в блоке всего три.
  const activeFormIdSet = new Set(activeFormIds ?? []);
  const nowForms = (formsData?.forms ?? []).filter((form) =>
    activeFormIdSet.has(form.id),
  );
  const lang = project?.lang ?? "ru";
  const sections = buildDocSections(
    docs,
    project?.authors ?? [],
    t("documents.sectionShared"),
  );
  // Командный проект = больше одной секции (общие + авторы). Соло всегда даёт
  // ровно одну плоскую секцию, и строка авторов там не рендерится вовсе.
  const isTeam = sections.length > 1;
  // Сохранённый выбор чистится от исчезнувших авторов, иначе список схлопнется
  // в пустоту после правки состава команды.
  const activeAuthorKeys = isTeam
    ? authorKeys.filter((key) =>
        sections.some((section) => section.key === key),
      )
    : [];
  const isAuthorVisible = (sectionKey: string): boolean =>
    activeAuthorKeys.length === 0 || activeAuthorKeys.includes(sectionKey);

  const needle = query.trim().toLowerCase();
  const visibleSections = sections
    .filter((section) => isAuthorVisible(section.key))
    .map((section) => ({
      key: section.key,
      title: section.title ?? t("documents.title"),
      rows: section.docs
        .map(
          (doc): DocSectionRow => ({
            doc,
            // Pass the whole doc: def_id resolves the type name for team
            // instances. Inside an author section the owner is already in the
            // header, so the row shows the bare type name.
            meta: getDocMeta(
              doc.id,
              section.hideOwnerSuffix ? { ...doc, owner_name: null } : doc,
              lang,
            ),
          }),
        )
        .filter(
          (row) =>
            matchesStatus(row.doc, statusChip) &&
            matchesQuery(row.meta, needle),
        ),
    }))
    .filter((section) => section.rows.length > 0);

  // Счётчики чипов считаются по набору, уже суженному авторами: иначе цифра
  // на чипе и длина списка расходятся.
  const chipDocs = sections
    .filter((section) => isAuthorVisible(section.key))
    .flatMap((section) => section.docs);
  const errorsCount = chipDocs.filter((doc) => doc.status === "err").length;
  const notBuiltCount = chipDocs.filter((doc) => doc.status === "draft").length;

  const isEveryCollapsed =
    sections.length > 0 &&
    sections.every((section) => collapsedKeys.includes(section.key));
  const isFiltered =
    needle !== "" || statusChip !== "all" || activeAuthorKeys.length > 0;
  // Пока фильтр прячет строки, свёрнутые группы раскрываются принудительно:
  // иначе найденное остаётся за закрытым заголовком и панель выглядит пустой.
  // Сам набор свёрнутых ключей при этом не трогаем — он вернётся после сброса.
  const isRowFilterActive = needle !== "" || statusChip !== "all";

  const handleBuildAll = () => {
    // Сборка остаётся проектной: фильтр прячет строки, а не документы.
    startAll(docs.map((doc) => doc.id));
  };

  const setCollapsedKeys = (next: string[]) => {
    setState({ ...panelState, collapsedKeys: next });
    writeStoredKeys(collapsedStorageKey(projectId), next);
  };

  const setAuthorKeys = (next: string[]) => {
    setState({ ...panelState, authorKeys: next });
    writeStoredKeys(authorsStorageKey(projectId), next);
  };

  const handleToggleSection = (sectionKey: string) => {
    setCollapsedKeys(
      collapsedKeys.includes(sectionKey)
        ? collapsedKeys.filter((key) => key !== sectionKey)
        : [...collapsedKeys, sectionKey],
    );
  };

  const handleCollapseAll = () => {
    setCollapsedKeys(
      isEveryCollapsed ? [] : sections.map((section) => section.key),
    );
  };

  const handleToggleAuthor = (sectionKey: string) => {
    setAuthorKeys(
      activeAuthorKeys.includes(sectionKey)
        ? activeAuthorKeys.filter((key) => key !== sectionKey)
        : [...activeAuthorKeys, sectionKey],
    );
  };

  const handleAllAuthors = () => {
    setAuthorKeys([]);
  };

  const handleStatusChip = (chip: StatusChip) => {
    setState({ ...panelState, statusChip: chip });
  };

  const handleQueryChange = (event: ChangeEvent<HTMLInputElement>) => {
    setState({ ...panelState, query: event.target.value });
  };

  const handleClearQuery = () => {
    setState({ ...panelState, query: "" });
  };

  const handleResetFilters = () => {
    setState({
      ...panelState,
      query: "",
      statusChip: "all",
      authorKeys: [],
    });
    writeStoredKeys(authorsStorageKey(projectId), []);
  };

  return (
    <div className="workbench-panel">
      <div className="panel-head">
        <span className="panel-head-title">{t("documents.title")}</span>
        <div className="panel-head-actions">
          <button
            type="button"
            className="icon-btn sm tt"
            data-tt={t("panel.collapseAllGroups")}
            aria-label={t("panel.collapseAllGroups")}
            onClick={handleCollapseAll}
            disabled={sections.length === 0}
          >
            {isEveryCollapsed ? (
              <ChevronsUpDown size={12} />
            ) : (
              <ChevronsDownUp size={12} />
            )}
          </button>
        </div>
      </div>

      <div className="panel-body">
        <div className="panel-filter">
          <Search size={12} style={{ flexShrink: 0, color: "var(--fg-3)" }} />
          <input
            type="text"
            value={query}
            onChange={handleQueryChange}
            placeholder={t("panel.filterPlaceholder")}
            aria-label={t("panel.filterPlaceholder")}
          />
          {query !== "" && (
            <button
              type="button"
              className="icon-btn sm"
              aria-label={t("panel.clearFilter")}
              onClick={handleClearQuery}
            >
              <X size={11} />
            </button>
          )}
        </div>

        <div className="fchip-row">
          <button
            type="button"
            className={clsx("fchip", statusChip === "all" && "active")}
            aria-pressed={statusChip === "all"}
            onClick={() => {
              handleStatusChip("all");
            }}
          >
            {t("documents.chipAll")}
            <span className="fchip-count">{chipDocs.length}</span>
          </button>
          {(errorsCount > 0 || statusChip === "errors") && (
            <button
              type="button"
              className={clsx("fchip", statusChip === "errors" && "active")}
              aria-pressed={statusChip === "errors"}
              onClick={() => {
                handleStatusChip(statusChip === "errors" ? "all" : "errors");
              }}
            >
              <span className="dot err" />
              {t("documents.chipErrors")}
              <span className="fchip-count">{errorsCount}</span>
            </button>
          )}
          {(notBuiltCount > 0 || statusChip === "notBuilt") && (
            <button
              type="button"
              className={clsx("fchip", statusChip === "notBuilt" && "active")}
              aria-pressed={statusChip === "notBuilt"}
              onClick={() => {
                handleStatusChip(
                  statusChip === "notBuilt" ? "all" : "notBuilt",
                );
              }}
            >
              {t("documents.chipNotBuilt")}
              <span className="fchip-count">{notBuiltCount}</span>
            </button>
          )}
        </div>

        {isTeam && (
          <div className="fchip-row">
            <button
              type="button"
              className={clsx(
                "fchip",
                activeAuthorKeys.length === 0 && "active",
              )}
              aria-pressed={activeAuthorKeys.length === 0}
              onClick={handleAllAuthors}
            >
              {t("documents.chipAuthorsAll")}
            </button>
            {sections.map((section) => {
              const label = section.title ?? t("documents.title");
              return (
                <button
                  key={section.key}
                  type="button"
                  className={clsx(
                    "fchip",
                    activeAuthorKeys.includes(section.key) && "active",
                  )}
                  aria-pressed={activeAuthorKeys.includes(section.key)}
                  title={label}
                  onClick={() => {
                    handleToggleAuthor(section.key);
                  }}
                >
                  {/* ФИО целиком не влезает в 260px — режем многоточием. */}
                  <span
                    className="truncate"
                    style={{ maxWidth: 104, minWidth: 0 }}
                  >
                    {label}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {onOpenForm && (
          <NowBlock
            documents={docs}
            forms={nowForms}
            lang={lang}
            onSelectDoc={onSelectDoc}
            onOpenForm={onOpenForm}
          />
        )}

        {isCompiling && isStalled && (
          <div
            className="flex items-start gap-2"
            style={{
              margin: "0 2px 8px",
              padding: "6px 8px",
              fontSize: 10.5,
              lineHeight: 1.4,
              background: "var(--c-err-soft, rgba(239, 68, 68, 0.08))",
              border: "1px solid var(--c-err)",
              color: "var(--c-err)",
              borderRadius: 4,
            }}
          >
            <AlertTriangle size={12} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>{t("documents.stalledWarning")}</span>
          </div>
        )}
        {isCompiling && !isStalled && (
          <div
            className="flex items-center gap-1"
            style={{
              margin: "0 2px 8px",
              fontSize: 10,
              color: "var(--fg-3)",
            }}
          >
            <RefreshCw size={9} className="spin" />
            <span>{t("documents.buildInProgress")}</span>
          </div>
        )}

        {visibleSections.map((section) => (
          <DocSection
            key={section.key}
            projectId={projectId}
            sectionKey={section.key}
            title={section.title}
            rows={section.rows}
            isCollapsed={
              !isRowFilterActive && collapsedKeys.includes(section.key)
            }
            query={query}
            selectedDocId={selectedDocId}
            onToggle={handleToggleSection}
            onSelectDoc={onSelectDoc}
            isDocBuilding={isDocBuilding}
          />
        ))}

        {isLoading && docs.length === 0 && (
          <div
            className="flex items-center justify-center gap-2"
            style={{ padding: "12px 0", fontSize: 11, color: "var(--fg-3)" }}
          >
            <Spinner size="sm" />
            <span>{t("panel.loading")}</span>
          </div>
        )}

        {!isLoading && docs.length === 0 && (
          <div
            style={{
              padding: "14px 10px",
              fontSize: 11.5,
              lineHeight: 1.45,
              color: "var(--fg-3)",
            }}
          >
            {t("documents.empty")}
          </div>
        )}

        {docs.length > 0 && visibleSections.length === 0 && (
          <div
            className="flex flex-col items-start gap-2"
            style={{ padding: "14px 10px" }}
          >
            <span style={{ fontSize: 12, color: "var(--fg-1)" }}>
              {t("panel.nothingFound")}
            </span>
            <span
              style={{ fontSize: 10.5, lineHeight: 1.4, color: "var(--fg-3)" }}
            >
              {t("panel.nothingFoundHint")}
            </span>
            {isFiltered && (
              <button
                type="button"
                className="btn xs"
                onClick={handleResetFilters}
              >
                {t("panel.resetFilters")}
              </button>
            )}
          </div>
        )}
      </div>

      {/* «Собрать всё» намеренно живёт в подвале и всегда на виду: это самое
          частое действие в панели, и прятать его под наведение (как остальные
          действия заголовка) значило бы экономить пиксели на главном. */}
      <div className="panel-foot">
        {isCompiling ? (
          <button
            type="button"
            className="btn xs"
            onClick={cancelAll}
            style={{
              justifyContent: "center",
              color: isStalled ? "var(--c-err)" : undefined,
              borderColor: isStalled ? "var(--c-err)" : undefined,
            }}
          >
            {isStalled ? <AlertTriangle size={11} /> : <Square size={11} />}
            {t("panel.stopBuilds")}
          </button>
        ) : (
          <button
            type="button"
            className="btn xs primary"
            onClick={handleBuildAll}
            disabled={docs.length === 0}
            style={{ justifyContent: "center" }}
          >
            <Play size={11} />
            {t("panel.buildAll")}
          </button>
        )}
        {isCompiling && isStalled && (
          <span
            style={{
              fontSize: 10,
              lineHeight: 1.4,
              color: "var(--c-err)",
            }}
          >
            {t("documents.stalledWarning")}
          </span>
        )}
      </div>
    </div>
  );
};
