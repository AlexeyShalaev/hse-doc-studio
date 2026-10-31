import { useState } from "react";
import { Download, Eye, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  artifactFileUrl,
  useDeleteProjectArtifact,
  useProjectArtifacts,
  type ProjectArtifact,
} from "@entities/project-artifact";
import { formatFileSize, formatRelativeTime, toast } from "@shared/lib";
import { Modal, PdfViewer } from "@shared/ui";

export type PdfArtifactsCardProps = {
  projectId: string;
  /** Может ли человек убирать выгруженные PDF (право записи; сервер проверит ещё раз). */
  canDelete?: boolean;
};

type ArtifactRowProps = {
  artifact: ProjectArtifact;
  canDelete: boolean;
  isDeleting: boolean;
  onOpen: () => void;
  onDelete: () => void;
};

const ArtifactRow = ({
  artifact,
  canDelete,
  isDeleting,
  onOpen,
  onDelete,
}: ArtifactRowProps) => {
  const { t } = useTranslation("workbench");
  const href = artifactFileUrl(artifact.file_url);
  const meta = [
    artifact.pages ? t("artifacts.pages", { count: artifact.pages }) : null,
    formatFileSize(artifact.size),
    t("artifacts.uploaded", { when: formatRelativeTime(artifact.uploaded_at) }),
    artifact.uploaded_by_name
      ? t("artifacts.by", { who: artifact.uploaded_by_name })
      : null,
    artifact.client_name
      ? t("artifacts.via", { client: artifact.client_name })
      : null,
  ].filter((part): part is string => part !== null);

  return (
    <div
      className="flex items-center justify-between"
      style={{ gap: 12 }}
      data-testid="artifact-row"
    >
      <div className="flex flex-col" style={{ gap: 2, minWidth: 0 }}>
        <strong style={{ fontSize: 12.5 }} className="truncate">
          {artifact.file_name}
        </strong>
        <span className="dim" style={{ fontSize: 11.5, lineHeight: 1.5 }}>
          {meta.join(" · ")}
        </span>
      </div>
      <div className="flex items-center" style={{ gap: 6, flexShrink: 0 }}>
        <button type="button" className="btn sm" onClick={onOpen}>
          <Eye size={13} aria-hidden="true" />
          {t("artifacts.open")}
        </button>
        <a className="btn sm" href={href} download={artifact.file_name}>
          <Download size={13} aria-hidden="true" />
          {t("artifacts.download")}
        </a>
        {canDelete && (
          <button
            type="button"
            className="icon-btn"
            aria-label={t("artifacts.delete")}
            title={t("artifacts.delete")}
            disabled={isDeleting}
            onClick={onDelete}
          >
            <Trash2 size={14} aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
};

/**
 * Карточка «PDF из локальной Студии» на странице проекта: последний выгруженный PDF
 * каждого документа и более ранние версии. Права на чтение те же, что у результата
 * сборки: бэкенд отдаёт список и файл только тем, кто видит проект.
 */
export const PdfArtifactsCard = ({
  projectId,
  canDelete = false,
}: PdfArtifactsCardProps) => {
  const { t } = useTranslation("workbench");
  const { data } = useProjectArtifacts(projectId);
  const remove = useDeleteProjectArtifact();
  const [viewing, setViewing] = useState<ProjectArtifact | null>(null);

  const items = data?.items ?? [];
  if (items.length === 0) return null;

  // Список приходит от новых к старым: первая запись документа это последняя версия.
  const latest = new Map<string, ProjectArtifact>();
  const older = new Map<string, ProjectArtifact[]>();
  for (const item of items) {
    if (latest.has(item.doc_id)) {
      older.set(item.doc_id, [...(older.get(item.doc_id) ?? []), item]);
    } else {
      latest.set(item.doc_id, item);
    }
  }

  const confirmDelete = (artifact: ProjectArtifact): void => {
    if (!window.confirm(t("artifacts.deleteConfirm"))) return;
    remove.mutate(
      { projectId, artifactId: artifact.id },
      {
        onError: () => {
          toast.error(t("artifacts.deleteFailed"));
        },
      },
    );
  };

  const row = (artifact: ProjectArtifact) => (
    <ArtifactRow
      key={artifact.id}
      artifact={artifact}
      canDelete={canDelete}
      isDeleting={remove.isPending}
      onOpen={() => {
        setViewing(artifact);
      }}
      onDelete={() => {
        confirmDelete(artifact);
      }}
    />
  );

  return (
    <div
      className="card"
      style={{
        padding: 18,
        display: "flex",
        flexDirection: "column",
        gap: 14,
        maxWidth: 860,
      }}
      data-testid="pdf-artifacts-card"
    >
      <div className="flex flex-col" style={{ gap: 4 }}>
        <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>
          {t("artifacts.title")}
        </h3>
        <span className="dim" style={{ fontSize: 12 }}>
          {t("artifacts.hint")}
        </span>
      </div>
      {[...latest.entries()].map(([docId, artifact]) => (
        <div key={docId} className="flex flex-col" style={{ gap: 8 }}>
          <span className="mono dim" style={{ fontSize: 11 }}>
            {docId}
          </span>
          {row(artifact)}
          {(older.get(docId)?.length ?? 0) > 0 && (
            <details>
              <summary className="dim" style={{ fontSize: 11.5 }}>
                {t("artifacts.older", { count: older.get(docId)?.length })}
              </summary>
              <div className="flex flex-col" style={{ gap: 8, paddingTop: 8 }}>
                {(older.get(docId) ?? []).map(row)}
              </div>
            </details>
          )}
        </div>
      ))}
      <Modal
        isOpen={viewing !== null}
        onClose={() => {
          setViewing(null);
        }}
        title={
          viewing
            ? t("artifacts.viewerTitle", {
                doc: viewing.doc_id,
                file: viewing.file_name,
              })
            : undefined
        }
        width={960}
      >
        {viewing && (
          <div style={{ height: "70vh", minHeight: 320 }}>
            <PdfViewer
              url={artifactFileUrl(viewing.file_url)}
              refreshKey={viewing.id}
              ariaLabel={viewing.file_name}
              storageKey={`artifact:${viewing.id}`}
            />
          </div>
        )}
      </Modal>
    </div>
  );
};
