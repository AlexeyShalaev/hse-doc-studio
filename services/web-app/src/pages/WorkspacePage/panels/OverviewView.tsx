import { useTranslation } from "react-i18next";
import { FileText, LayoutDashboard } from "lucide-react";
import { useDocuments } from "@entities/document";
import { useProject } from "@entities/project";
import { useCapabilities } from "@entities/session";
import { PdfArtifactsCard } from "@features/project-artifacts";
import { TemplateUpdateCard } from "@features/template-update";
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
  <div className="flex items-center" style={{ gap: "0.5rem" }}>
    <span className={`dot ${sev}`} />
    <span
      className="mono"
      style={{ fontSize: "0.8125rem", minWidth: "1.375rem" }}
    >
      {count}
    </span>
    <span className="dim" style={{ fontSize: "0.78125rem" }}>
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
  const { has } = useCapabilities();
  const { data: project } = useProject(projectId);

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
      style={{
        padding: "1.5rem 2rem",
        overflowY: "auto",
        flex: 1,
        minHeight: 0,
      }}
    >
      <PageHead
        icon={LayoutDashboard}
        title={t("overview.title")}
        sub={t("overview.subtitle")}
      />

      <div style={{ marginTop: "1.25rem" }}>
        <TemplateUpdateCard projectId={projectId} />
      </div>

      <div
        style={{
          marginTop: "1.5rem",
          display: "grid",
          gap: "0.875rem",
          gridTemplateColumns: "repeat(auto-fit, minmax(16.25rem, 1fr))",
          maxWidth: "53.75rem",
        }}
      >
        <SectionCard title={t("overview.documentsSummary")}>
          {isLoading ? (
            <div className="flex items-center" style={{ gap: "0.5rem" }}>
              <Spinner size="sm" />
              <span className="dim" style={{ fontSize: "0.78125rem" }}>
                {t("panel.loading")}
              </span>
            </div>
          ) : total === 0 ? (
            <p className="dim" style={{ margin: 0, fontSize: "0.78125rem" }}>
              {t("overview.noDocuments")}
            </p>
          ) : (
            <>
              <span
                className="mono"
                style={{ fontSize: "1.875rem", fontWeight: 600, lineHeight: 1 }}
              >
                {total}
              </span>
              <div className="flex flex-col" style={{ gap: "0.4375rem" }}>
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

      {has("git_remote") && (
        <div style={{ marginTop: "0.875rem" }}>
          <PdfArtifactsCard
            projectId={projectId}
            canDelete={project?.access?.mode === "full"}
          />
        </div>
      )}

      {firstDoc && (
        <button
          type="button"
          className="btn primary"
          style={{ marginTop: "1.25rem" }}
          onClick={() => {
            onSelectDoc(firstDoc.id);
          }}
        >
          <FileText size="0.8125rem" />
          {t("overview.openLastDoc")}
        </button>
      )}
    </div>
  );
};
