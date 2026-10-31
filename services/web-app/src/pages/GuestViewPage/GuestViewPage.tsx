import { useParams } from "react-router";
import { useDocuments } from "@entities/document";
import { useProject } from "@entities/project";
import { env } from "@shared/config";
import { i18n, pickLocalized } from "@shared/lib";
import { AppTitlebar } from "@widgets/AppTitlebar";
import { GuestView, type GuestViewDoc } from "./GuestView";

const pdfUrl = (projectId: string, docId: string, compileId: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/documents/${docId}/compiles/${compileId}/pdf`;

/** `/projects/:projectId/view`: просмотр PDF для читателя без исходников (гостя или вошедшего). */
export const GuestViewPage = () => {
  const { projectId = "" } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  const documents = useDocuments(projectId);
  const docs: GuestViewDoc[] = (documents.data ?? []).map((doc) => ({
    id: doc.id,
    name: pickLocalized(
      doc.name ?? undefined,
      i18n.language,
      doc.def_id ?? doc.id,
    ),
    pdfUrl:
      doc.last_compile_id && (doc.status === "ok" || doc.status === "warn")
        ? pdfUrl(projectId, doc.id, doc.last_compile_id)
        : null,
    pages: doc.pages ?? null,
  }));
  return (
    <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
      <AppTitlebar projectName={project.data?.name ?? null} />
      <div style={{ overflow: "auto", flex: 1 }}>
        <GuestView
          projectName={project.data?.name ?? ""}
          status={
            documents.data ? "ready" : documents.isError ? "error" : "loading"
          }
          docs={docs}
          onRetry={() => {
            void documents.refetch();
          }}
        />
      </div>
    </div>
  );
};
