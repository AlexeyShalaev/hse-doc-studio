import type React from "react";
import { useState } from "react";
import { AlertTriangle, Play, ShieldCheck, Square } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import type { z } from "zod";
import type { DocStatus, DocumentResponseSchema } from "@entities/document";
import { getDocMeta, getStatusMeta, useDocuments } from "@entities/document";
import {
  useCancelProjectCompiles,
  useCompileStreamStore,
  useIsProjectStalled,
  useStartCompileAll,
} from "@entities/compile";
import { useProject } from "@entities/project";
import { Spinner } from "@shared/ui";

// Проектный навигатор качества: панель отвечает на вопрос «в КАКИХ документах
// беда» и прыгает туда, а разбор конкретных строк лога остаётся канвасу
// документа. Поэтому здесь нет ни одной строки LaTeX-лога — только документы,
// их счётчики и статус последней сборки.

type DocumentItem = z.infer<typeof DocumentResponseSchema>;

type ReviewTab = "errors" | "warnings" | "builds";

// Единый порядок для обеих «проблемных» вкладок: список не перетасовывается при
// переключении фильтра — глаз держит те же строки на тех же местах.
const byIssues = (a: DocumentItem, b: DocumentItem): number =>
  (b.errors ?? 0) - (a.errors ?? 0) || (b.warnings ?? 0) - (a.warnings ?? 0);

// Вкладка «Сборки» сортирует по статусу: сначала то, что требует внимания,
// «собрано без замечаний» — в самом низу.
const BUILD_ORDER: Record<DocStatus, number> = {
  err: 0,
  warn: 1,
  building: 2,
  draft: 3,
  locked: 4,
  ok: 5,
};

type ReviewRowProps = {
  code: string;
  name: string;
  sev: "ok" | "warn" | "err" | "info";
  errors: number;
  warnings: number;
  // Показывается вместо счётчика, когда замечаний нет (вкладка «Сборки»).
  statusLabel: string | null;
  countsTitle: string;
  isActive: boolean;
  onSelect: () => void;
};

// Ровно тот же визуальный язык, что и строка документа в DocumentNav: точка
// статуса → mono-код → название → mono-счётчик «2E 1W».
const ReviewRow = ({
  code,
  name,
  sev,
  errors,
  warnings,
  statusLabel,
  countsTitle,
  isActive,
  onSelect,
}: ReviewRowProps) => {
  const hasCounts = errors > 0 || warnings > 0;
  return (
    <button
      type="button"
      className={clsx("row-btn", isActive && "active")}
      onClick={onSelect}
      style={{ alignItems: "center", gap: 8 }}
    >
      <span className={"dot " + sev} />
      <span
        className="mono"
        style={{
          flexShrink: 0,
          fontSize: 10.5,
          color: isActive ? "var(--accent)" : "var(--fg-3)",
          // Выравнивает колонку кодов: длинный код сдвигает название, а не
          // наезжает на него.
          minWidth: 28,
          whiteSpace: "nowrap",
          letterSpacing: "0.02em",
        }}
      >
        {code}
      </span>
      <span
        className="truncate"
        style={{ flex: 1, minWidth: 0, fontSize: 12, lineHeight: 1.35 }}
      >
        {name}
      </span>
      {hasCounts && (
        <span
          className="mono"
          title={countsTitle}
          style={{
            flexShrink: 0,
            fontSize: 9.5,
            color: errors > 0 ? "var(--c-err)" : "var(--c-warn)",
            letterSpacing: "0.04em",
          }}
        >
          {errors > 0 ? `${String(errors)}E` : ""}
          {errors > 0 && warnings > 0 ? " " : ""}
          {warnings > 0 ? `${String(warnings)}W` : ""}
        </span>
      )}
      {!hasCounts && statusLabel != null && (
        <span
          className="mono dim"
          style={{ flexShrink: 0, fontSize: 9.5, letterSpacing: "0.04em" }}
        >
          {statusLabel}
        </span>
      )}
    </button>
  );
};

export type ReviewPanelProps = {
  projectId: string;
  selectedDocId?: string | undefined;
  onSelectDoc: (docId: string) => void;
};

export const ReviewPanel = ({
  projectId,
  selectedDocId,
  onSelectDoc,
}: ReviewPanelProps) => {
  const { t } = useTranslation("workbench");
  const [tab, setTab] = useState<ReviewTab>("errors");
  const { data: project } = useProject(projectId);
  const { data: documents, isLoading } = useDocuments(projectId);
  const { startAll, isRunning: isCompiling } = useStartCompileAll(projectId);
  const { cancelAll } = useCancelProjectCompiles(projectId);
  const isStalled = useIsProjectStalled(projectId);
  const compileStreams = useCompileStreamStore((s) => s.streams);

  const lang = project?.lang ?? "ru";
  const docs = documents ?? [];
  const isDocBuilding = (docId: string): boolean =>
    compileStreams[`${projectId}::${docId}`]?.status === "running";

  const withIssues = docs
    .filter((doc) => (doc.errors ?? 0) + (doc.warnings ?? 0) > 0)
    .sort(byIssues);
  const rowsByTab: Record<ReviewTab, DocumentItem[]> = {
    errors: withIssues.filter((doc) => (doc.errors ?? 0) > 0),
    warnings: withIssues.filter((doc) => (doc.warnings ?? 0) > 0),
    builds: [...docs].sort(
      (a, b) => BUILD_ORDER[a.status] - BUILD_ORDER[b.status] || byIssues(a, b),
    ),
  };
  const rows = rowsByTab[tab];

  const tabs: { id: ReviewTab; label: string; count: number }[] = [
    {
      id: "errors",
      label: t("review.tabErrors"),
      count: rowsByTab.errors.length,
    },
    {
      id: "warnings",
      label: t("review.tabWarnings"),
      count: rowsByTab.warnings.length,
    },
    {
      id: "builds",
      label: t("review.tabBuilds"),
      count: rowsByTab.builds.length,
    },
  ];

  const handleBuildAll = () => {
    startAll(docs.map((doc) => doc.id));
  };

  let content: React.ReactNode;
  if (isLoading && docs.length === 0) {
    content = (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 8,
          padding: "24px 0",
        }}
      >
        <Spinner size="sm" />
        <span className="dim" style={{ fontSize: 11.5 }}>
          {t("panel.loading")}
        </span>
      </div>
    );
  } else if (rows.length === 0) {
    content = (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 6,
          padding: "34px 14px",
          textAlign: "center",
        }}
      >
        <ShieldCheck size={18} style={{ color: "var(--fg-3)" }} />
        <span style={{ fontSize: 12.5, color: "var(--fg-2)" }}>
          {t("review.empty")}
        </span>
        <span className="dim" style={{ fontSize: 11, lineHeight: 1.45 }}>
          {t("review.emptyHint")}
        </span>
      </div>
    );
  } else {
    content = rows.map((doc) => {
      const meta = getDocMeta(doc.id, doc, lang);
      const status: DocStatus =
        isDocBuilding(doc.id) || doc.status === "building"
          ? "building"
          : doc.status;
      const statusMeta = getStatusMeta(status);
      const errors = doc.errors ?? 0;
      const warnings = doc.warnings ?? 0;
      const countsTitle = [
        errors > 0 ? t("review.errorsCount", { count: errors }) : null,
        warnings > 0 ? t("review.warningsCount", { count: warnings }) : null,
      ]
        .filter((part) => part !== null)
        .join(" · ");
      return (
        <ReviewRow
          key={doc.id}
          code={meta.code}
          name={meta.name}
          sev={statusMeta.sev}
          errors={errors}
          warnings={warnings}
          // Счётчик важнее ярлыка статуса; ярлык подставляется только там, где
          // считать нечего — на вкладке «Сборки».
          statusLabel={tab === "builds" ? statusMeta.label : null}
          countsTitle={countsTitle}
          isActive={selectedDocId === doc.id}
          onSelect={() => {
            onSelectDoc(doc.id);
          }}
        />
      );
    });
  }

  return (
    <div className="workbench-panel">
      <div className="panel-head">
        <span className="panel-head-title">{t("review.title")}</span>
        <div className="panel-head-actions">
          {isCompiling ? (
            <button
              type="button"
              className="icon-btn sm tt"
              data-tt={t("panel.stopBuilds")}
              onClick={cancelAll}
              style={{ color: isStalled ? "var(--c-err)" : undefined }}
            >
              {isStalled ? <AlertTriangle size={12} /> : <Square size={12} />}
            </button>
          ) : (
            <button
              type="button"
              className="icon-btn sm tt"
              data-tt={t("panel.buildAll")}
              onClick={handleBuildAll}
              disabled={docs.length === 0}
            >
              <Play size={12} />
            </button>
          )}
        </div>
      </div>

      <div className="panel-body">
        <div
          className="seg"
          style={{ display: "flex", width: "100%", marginBottom: 8 }}
        >
          {tabs.map((item) => (
            <button
              key={item.id}
              type="button"
              className={clsx(tab === item.id && "active")}
              aria-pressed={tab === item.id}
              onClick={() => {
                setTab(item.id);
              }}
              style={{ flex: 1, minWidth: 0, padding: "4px 6px" }}
            >
              <span className="truncate">{item.label}</span>
              <span className="mono" style={{ fontSize: 9.5, opacity: 0.75 }}>
                {String(item.count)}
              </span>
            </button>
          ))}
        </div>
        {content}
      </div>
    </div>
  );
};
