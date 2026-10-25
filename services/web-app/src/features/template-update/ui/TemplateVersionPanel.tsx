import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  ArrowUpCircle,
  CheckCircle2,
  Eye,
  EyeOff,
  RotateCcw,
} from "lucide-react";
import { Modal } from "@shared/ui";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";
import {
  type AvailableUpdate,
  useCompareWithTemplate,
  useRevertTemplateUpdate,
  useSetTemplateTracking,
  useTemplateUpdateStatus,
} from "@entities/template-update";
import { TemplateFileDiff } from "./TemplateFileDiff";
import { TemplateUpdateDialog } from "./TemplateUpdateDialog";
import { breakingOf, classTone, notesOf } from "./templateUpdate.model";

export type TemplateVersionPanelProps = {
  projectId: string;
  /** Проект только для чтения: обновлять и отменять нельзя, смотреть — можно. */
  isReadOnly: boolean;
};

/**
 * Версия шаблона проекта: доступные обновления с заметками, отмена последнего
 * обновления и «Сравнить с шаблоном» — что пользователь правил в файлах шаблона.
 */
export const TemplateVersionPanel = ({
  projectId,
  isReadOnly,
}: TemplateVersionPanelProps) => {
  const { t, i18n } = useTranslation("templateUpdate");
  const { data: status, isLoading } = useTemplateUpdateStatus(projectId);
  const [target, setTarget] = useState<AvailableUpdate | null>(null);
  const [isRevertOpen, setIsRevertOpen] = useState(false);
  const revert = useRevertTemplateUpdate();

  if (isLoading || !status) {
    return <Spinner size="sm" />;
  }

  const last = status.last_update;
  const handleRevert = () => {
    revert.mutate(
      { projectId, params: last ? { update_id: last.id } : {} },
      {
        onSuccess: (result) => {
          toast.success(
            result.kept.length > 0
              ? t("section.revertKept", { count: result.kept.length })
              : t("section.revertDone"),
          );
          setIsRevertOpen(false);
        },
      },
    );
  };

  return (
    <div className="flex flex-col" style={{ gap: 14 }}>
      <div className="flex items-center" style={{ gap: 8, fontSize: 12.5 }}>
        <span>{t("section.current", { version: status.current_version })}</span>
        {status.current && (
          <span className="badge" style={{ fontSize: 10.5 }}>
            {status.current.released
              ? t("section.released")
              : t("section.draft")}
          </span>
        )}
      </div>
      {status.in_progress && (
        <span className="dim" style={{ fontSize: 12 }}>
          {t("section.inProgress")}
        </span>
      )}
      {status.digest_mismatch && (
        <Hint icon="warn" text={t("section.digestMismatch")} />
      )}
      {status.unresolved_markers.length > 0 && (
        <div className="flex flex-col" style={{ gap: 4, fontSize: 12 }}>
          <Hint icon="warn" text={t("section.markers")} />
          {status.unresolved_markers.map((path) => (
            <span key={path} className="mono" style={{ paddingLeft: 22 }}>
              {path}
            </span>
          ))}
        </div>
      )}

      {status.available.length === 0 ? (
        <Hint icon="ok" text={t("section.upToDate")} />
      ) : (
        <div className="flex flex-col" style={{ gap: 10 }}>
          <strong style={{ fontSize: 12 }}>{t("section.available")}</strong>
          {status.available.map((update) => {
            const notes = notesOf(update, i18n.language);
            const breaking = breakingOf(update, i18n.language);
            return (
              <div
                key={update.version.version}
                className="card"
                style={{
                  padding: 12,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div className="flex items-center" style={{ gap: 8 }}>
                  <strong className="mono" style={{ fontSize: 12.5 }}>
                    {update.version.version}
                  </strong>
                  {update.update_class && (
                    <span
                      className="badge"
                      style={{
                        fontSize: 10.5,
                        color: classTone(update.update_class),
                      }}
                    >
                      {t(`class.${update.update_class}`)}
                    </span>
                  )}
                  <span className="dim" style={{ fontSize: 11, flex: 1 }}>
                    {update.version.released_at}
                  </span>
                  <button
                    type="button"
                    className="btn xs"
                    disabled={isReadOnly || status.in_progress}
                    onClick={() => {
                      setTarget(update);
                    }}
                  >
                    <ArrowUpCircle size={11} />
                    {t("section.review")}
                  </button>
                </div>
                {notes.length > 0 && (
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
                    {notes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                )}
                {breaking.length > 0 && (
                  <div className="flex flex-col" style={{ gap: 2 }}>
                    <span
                      style={{
                        fontSize: 11.5,
                        color: "var(--c-err)",
                        fontWeight: 600,
                      }}
                    >
                      {t("section.breaking")}
                    </span>
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
                      {breaking.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {last && (
        <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
          <span style={{ flex: 1 }}>
            {t("section.lastUpdate", {
              from: last.from_version,
              to: last.to_version,
            })}
          </span>
          <button
            type="button"
            className="btn xs"
            disabled={isReadOnly || status.in_progress}
            onClick={() => {
              setIsRevertOpen(true);
            }}
          >
            <RotateCcw size={11} />
            {t("section.revert")}
          </button>
        </div>
      )}

      <CompareWithTemplate projectId={projectId} isReadOnly={isReadOnly} />

      <TemplateUpdateDialog
        projectId={projectId}
        update={target}
        onClose={() => {
          setTarget(null);
        }}
      />
      <Modal
        isOpen={isRevertOpen && last !== null && last !== undefined}
        onClose={() => {
          setIsRevertOpen(false);
        }}
        title={t("section.revertConfirmTitle")}
        width={460}
        footer={
          <div className="flex justify-end" style={{ gap: 8 }}>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setIsRevertOpen(false);
              }}
              disabled={revert.isPending}
            >
              {t("dialog.cancel")}
            </button>
            <button
              type="button"
              className="btn primary"
              onClick={handleRevert}
              disabled={revert.isPending}
            >
              {revert.isPending ? (
                <Spinner size="sm" />
              ) : (
                <RotateCcw size={13} />
              )}
              {t("section.revert")}
            </button>
          </div>
        }
      >
        <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5 }}>
          {t("section.revertConfirmText", {
            version: last?.from_version ?? "",
          })}
        </p>
      </Modal>
    </div>
  );
};

const CompareWithTemplate = ({
  projectId,
  isReadOnly,
}: {
  projectId: string;
  isReadOnly: boolean;
}) => {
  const { t } = useTranslation("templateUpdate");
  const [isShown, setIsShown] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const { data, isLoading } = useCompareWithTemplate(projectId, isShown);
  const tracking = useSetTemplateTracking();

  return (
    <div className="flex flex-col" style={{ gap: 8 }}>
      <div className="flex items-center" style={{ gap: 8 }}>
        <strong style={{ fontSize: 12, flex: 1 }}>{t("compare.title")}</strong>
        {!isShown && (
          <button
            type="button"
            className="btn xs"
            onClick={() => {
              setIsShown(true);
            }}
          >
            <Eye size={11} />
            {t("compare.show")}
          </button>
        )}
      </div>
      <span className="dim" style={{ fontSize: 11.5 }}>
        {t("compare.hint")}
      </span>
      {isShown && isLoading && <Spinner size="sm" />}
      {isShown && data?.files.length === 0 && (
        <Hint icon="ok" text={t("compare.none")} />
      )}
      {isShown &&
        data?.files.map((file) => (
          <div key={file.path} className="flex flex-col" style={{ gap: 6 }}>
            <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
              <button
                type="button"
                className="mono truncate"
                style={{
                  flex: 1,
                  textAlign: "left",
                  background: "none",
                  border: 0,
                  padding: 0,
                  cursor: "pointer",
                  color: "var(--fg-0)",
                }}
                title={file.path}
                onClick={() => {
                  setSelected(selected === file.path ? null : file.path);
                }}
              >
                {file.path}
              </button>
              <span className="dim" style={{ fontSize: 11 }}>
                {file.ignored
                  ? t("compare.ignored")
                  : t(`compare.${file.status}`)}
              </span>
              {file.approximate && (
                <span title={t("compare.approximateHint")}>
                  <AlertTriangle size={11} style={{ color: "var(--c-warn)" }} />
                </span>
              )}
              <button
                type="button"
                className="btn xs"
                disabled={isReadOnly || tracking.isPending}
                title={file.ignored ? undefined : t("compare.untrackHint")}
                onClick={() => {
                  tracking.mutate({
                    projectId,
                    path: file.path,
                    tracked: file.ignored,
                  });
                }}
              >
                {file.ignored ? <Eye size={11} /> : <EyeOff size={11} />}
                {file.ignored ? t("compare.track") : t("compare.untrack")}
              </button>
            </div>
            {selected === file.path && file.status === "modified" && (
              <TemplateFileDiff
                projectId={projectId}
                path={file.path}
                view="mine"
              />
            )}
          </div>
        ))}
    </div>
  );
};

const Hint = ({ icon, text }: { icon: "ok" | "warn"; text: string }) => (
  <div className="flex items-start" style={{ gap: 8, fontSize: 12 }}>
    {icon === "ok" ? (
      <CheckCircle2
        size={13}
        style={{ color: "var(--c-ok)", flexShrink: 0, marginTop: 1 }}
      />
    ) : (
      <AlertTriangle
        size={13}
        style={{ color: "var(--c-warn)", flexShrink: 0, marginTop: 1 }}
      />
    )}
    <span>{text}</span>
  </div>
);
