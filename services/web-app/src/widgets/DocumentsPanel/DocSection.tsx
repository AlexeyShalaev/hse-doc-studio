import { Fragment } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { DocMeta } from "@entities/document";
import { DocRow } from "./DocRow";
import type { DocumentItem } from "./lib/buildDocSections";

// Pack-объявленный doc.group раньше рисовал только 1px-разделитель. Здесь он
// становится подписанной подгруппой; неизвестные идентификаторы падают в
// «Прочее», чтобы новый блок из пака не исчезал молча.
const GROUP_TITLE_KEYS: Record<string, string> = {
  espd: "documents.groupEspd",
  report: "documents.groupReport",
  work: "documents.groupWork",
  pdp: "documents.groupPdp",
  pres: "documents.groupPres",
  nda: "documents.groupNda",
};

export type DocSectionRow = {
  doc: DocumentItem;
  meta: DocMeta;
};

export type DocSectionProps = {
  projectId: string;
  /** Стабильный ключ секции (`shared` / `author:<slug>` / `all`). */
  sectionKey: string;
  title: string;
  rows: DocSectionRow[];
  isCollapsed: boolean;
  query: string;
  selectedDocId?: string | undefined;
  onToggle: (sectionKey: string) => void;
  onSelectDoc: (docId: string) => void;
  isDocBuilding: (docId: string) => boolean;
};

export const DocSection = ({
  projectId,
  sectionKey,
  title,
  rows,
  isCollapsed,
  query,
  selectedDocId,
  onToggle,
  onSelectDoc,
  isDocBuilding,
}: DocSectionProps) => {
  const { t } = useTranslation("workbench");
  const listId = `doc-section-${sectionKey.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  // Роллап живой: он и есть замена снятого из шапки счётчика ok/warn/err,
  // поэтому считается по тем строкам, что сейчас в секции.
  const okCount = rows.filter((row) => row.doc.status === "ok").length;
  const warnCount = rows.filter((row) => row.doc.status === "warn").length;
  const errCount = rows.filter((row) => row.doc.status === "err").length;

  const handleToggle = () => {
    onToggle(sectionKey);
  };

  return (
    <div>
      <button
        type="button"
        className="nav-group"
        onClick={handleToggle}
        aria-expanded={!isCollapsed}
        aria-controls={listId}
      >
        {isCollapsed ? <ChevronRight size={11} /> : <ChevronDown size={11} />}
        <span className="nav-group-title">{title}</span>
        <span className="nav-group-rollup">
          {okCount > 0 && (
            <span title={t("documents.rollupOk")}>
              <span className="dot ok" />
              {okCount}
            </span>
          )}
          {warnCount > 0 && (
            <span title={t("documents.rollupWarn")}>
              <span className="dot warn" />
              {warnCount}
            </span>
          )}
          {errCount > 0 && (
            <span title={t("documents.rollupErr")}>
              <span className="dot err" />
              {errCount}
            </span>
          )}
        </span>
      </button>
      {!isCollapsed && (
        <div id={listId}>
          {rows.map((row, index) => {
            const group = row.doc.group ?? null;
            const prevGroup =
              index > 0 ? (rows[index - 1]?.doc.group ?? null) : null;
            // Подпись рисуется только у документов с группой: у безгруппных
            // (титул, NDA соло) заголовка нет — как и раньше не было.
            const showGroupTitle = group != null && group !== prevGroup;
            return (
              <Fragment key={row.doc.id}>
                {showGroupTitle && (
                  <div className="nav-sub">
                    {t(GROUP_TITLE_KEYS[group] ?? "documents.groupOther")}
                  </div>
                )}
                <DocRow
                  projectId={projectId}
                  doc={row.doc}
                  meta={row.meta}
                  isActive={selectedDocId === row.doc.id}
                  isBuilding={
                    isDocBuilding(row.doc.id) || row.doc.status === "building"
                  }
                  query={query}
                  onSelectDoc={onSelectDoc}
                />
              </Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
};
