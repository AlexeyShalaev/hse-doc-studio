import { useTranslation } from "react-i18next";
import { FileText, LayoutDashboard } from "lucide-react";
import { useDocuments } from "@entities/document";
import { Spinner } from "@shared/ui";
import { PageHead } from "./PageHead";
import { SectionCard } from "./SectionCard";

export type OverviewViewProps = {
  projectId: string;
  onSelectDoc: (docId: string) => void;
};

type StatusRowProps = {
  sev: "ok" | "warn" | "err";
  count: number;
  label: string;
};

const StatusRow = ({ sev, count, label }: StatusRowProps) => (
  <div className="flex items-center" style={{ gap: 8 }}>
    <span className={`dot ${sev}`} />
    <span className="mono" style={{ fontSize: 13, minWidth: 22 }}>
      {count}
    </span>
    <span className="dim" style={{ fontSize: 12.5 }}>
      {label}
    </span>
  </div>
);

/**
 * The canvas shown at /projects/:id/documents when no document is selected.
 * Replaces the old dead-end empty state: a real status read-out of the project
 * plus one obvious way back into the work.
 */
export const OverviewView = ({ projectId, onSelectDoc }: OverviewViewProps) => {
  const { t } = useTranslation("workbench");
  const { data: documents, isLoading } = useDocuments(projectId);

  const docs = documents ?? [];
  const total = docs.length;
  const ok = docs.filter((doc) => doc.status === "ok").length;
  const warn = docs.filter((doc) => doc.status === "warn").length;
  const err = docs.filter((doc) => doc.status === "err").length;
  // «Продолжить работу» opens the first document — the same one the nav lists
  // on top, so the button lands where the eye already expects to go.
  const firstDoc = docs[0] ?? null;

  return (
    <div
      style={{ padding: "24px 32px", overflowY: "auto", flex: 1, minHeight: 0 }}
    >
      <PageHead
        icon={LayoutDashboard}
        title={t("overview.title")}
        sub={t("overview.subtitle")}
      />

      <div
        style={{
          marginTop: 24,
          display: "grid",
          gap: 14,
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          maxWidth: 860,
        }}
      >
        <SectionCard title={t("overview.documentsSummary")}>
          {isLoading ? (
            <div className="flex items-center" style={{ gap: 8 }}>
              <Spinner size="sm" />
              <span className="dim" style={{ fontSize: 12.5 }}>
                {t("panel.loading")}
              </span>
            </div>
          ) : total === 0 ? (
            <p className="dim" style={{ margin: 0, fontSize: 12.5 }}>
              {t("overview.noDocuments")}
            </p>
          ) : (
            <>
              <span
                className="mono"
                style={{ fontSize: 30, fontWeight: 600, lineHeight: 1 }}
              >
                {total}
              </span>
              <div className="flex flex-col" style={{ gap: 7 }}>
                <StatusRow
                  sev="ok"
                  count={ok}
                  label={t("documents.rollupOk")}
                />
                <StatusRow
                  sev="warn"
                  count={warn}
                  label={t("documents.rollupWarn")}
                />
                <StatusRow
                  sev="err"
                  count={err}
                  label={t("documents.rollupErr")}
                />
              </div>
            </>
          )}
        </SectionCard>
      </div>

      {firstDoc && (
        <button
          type="button"
          className="btn primary"
          style={{ marginTop: 20 }}
          onClick={() => {
            onSelectDoc(firstDoc.id);
          }}
        >
          <FileText size={13} />
          {t("overview.openLastDoc")}
        </button>
      )}
    </div>
  );
};
