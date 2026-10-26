import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, ArrowUpCircle, ShieldCheck } from "lucide-react";
import { Modal, Select } from "@shared/ui";
import { Spinner } from "@shared/ui/Spinner";
import {
  ActionTag,
  CountBadges,
  FileList,
  FileRowShell,
  Notice,
  ViewTabs,
} from "@shared/ui/ConflictKit";
import { ApiError } from "@shared/api";
import { toast } from "@shared/lib";
import {
  type AvailableUpdate,
  type ConflictResolution,
  type TemplateDiffView,
  type TemplateFileOp,
  useApplyTemplateUpdate,
  useTemplateUpdatePlan,
} from "@entities/template-update";
import { TemplateFileDiff } from "./TemplateFileDiff";
import {
  actionTone,
  countOrder,
  defaultResolution,
  notesOf,
  sortOps,
} from "./templateUpdate.model";

export type TemplateUpdateDialogProps = {
  projectId: string;
  /** Целевая версия; null — окно закрыто. */
  update: AvailableUpdate | null;
  onClose: () => void;
};

const VIEWS: TemplateDiffView[] = ["template", "mine", "result"];

// Для файлов без «моего» содержимого или без шаблона часть видов пуста.
const viewsFor = (op: TemplateFileOp): TemplateDiffView[] => {
  if (op.action === "add" || op.action === "user_deleted") return ["template"];
  if (op.action === "delete" || op.action === "orphan") return ["mine"];
  return VIEWS;
};

/**
 * Предпросмотр обновления шаблона: что станет с каждым файлом, дифф по файлу,
 * решение по конфликтам — и применение ровно того плана, который показан.
 */
export const TemplateUpdateDialog = ({
  projectId,
  update,
  onClose,
}: TemplateUpdateDialogProps) => {
  const { t, i18n } = useTranslation("templateUpdate");
  const toVersion = update?.version.version ?? null;
  const plan = useTemplateUpdatePlan(projectId, toVersion);
  const apply = useApplyTemplateUpdate();
  // Выбор файла и решения по конфликтам принадлежат конкретному плану: новый план
  // (другая версия или перезапрос после «устарел») начинает с чистого листа.
  const fingerprint = plan.data?.fingerprint ?? "";
  const [choice, setChoice] = useState<{
    fingerprint: string;
    selected: string | null;
    resolutions: Record<string, ConflictResolution>;
  }>({ fingerprint: "", selected: null, resolutions: {} });
  const current =
    choice.fingerprint === fingerprint
      ? choice
      : { fingerprint, selected: null, resolutions: {} };
  const selected = current.selected;
  const resolutions = current.resolutions;
  const [view, setView] = useState<TemplateDiffView>("template");
  const [outdated, setOutdated] = useState(false);

  const ops = useMemo(() => sortOps(plan.data?.files ?? []), [plan.data]);
  const selectedOp = ops.find((op) => op.path === selected) ?? null;
  const notes = update ? notesOf(update, i18n.language) : [];

  const resolutionOf = (op: TemplateFileOp): ConflictResolution =>
    resolutions[op.path] ?? defaultResolution(op);

  const handleApply = () => {
    if (!plan.data) return;
    const chosen: Record<string, ConflictResolution> = {};
    for (const op of ops) {
      if (op.action === "conflict") chosen[op.path] = resolutionOf(op);
    }
    apply.mutate(
      {
        projectId,
        params: {
          to_version: plan.data.to_version,
          fingerprint: plan.data.fingerprint,
          resolutions: chosen,
        },
      },
      {
        onSuccess: (result) => {
          toast.success(
            result.markers.length > 0
              ? t("dialog.appliedMarkers")
              : t("dialog.applied", { version: result.record.to_version }),
          );
          onClose();
        },
        onError: (error) => {
          if (error instanceof ApiError && error.status === 409) {
            setOutdated(true);
            void plan.refetch();
          }
        },
      },
    );
  };

  const provenanceNote =
    plan.data && plan.data.provenance !== "recorded"
      ? t(`dialog.provenance.${plan.data.provenance}`)
      : "";

  return (
    <Modal
      isOpen={update !== null}
      onClose={onClose}
      width={920}
      title={
        plan.data
          ? t("dialog.title", {
              from: plan.data.from_version,
              to: plan.data.to_version,
            })
          : (toVersion ?? "")
      }
      footer={
        <div className="flex items-center" style={{ gap: 8 }}>
          <span
            className="dim flex items-center"
            style={{ gap: 6, fontSize: 11, flex: 1 }}
          >
            <ShieldCheck size={12} />
            {t("dialog.safety")}
          </span>
          <button
            type="button"
            className="btn"
            onClick={onClose}
            disabled={apply.isPending}
          >
            {t("dialog.cancel")}
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={handleApply}
            disabled={!plan.data || apply.isPending || plan.isFetching}
          >
            {apply.isPending ? (
              <Spinner size="sm" />
            ) : (
              <ArrowUpCircle size={13} />
            )}
            {apply.isPending ? t("dialog.applying") : t("dialog.apply")}
          </button>
        </div>
      }
    >
      {plan.isLoading ? (
        <div className="flex items-center" style={{ gap: 8, padding: 16 }}>
          <Spinner size="sm" />
          <span className="dim" style={{ fontSize: 12 }}>
            {t("dialog.loading")}
          </span>
        </div>
      ) : plan.isError || !plan.data ? (
        <div style={{ padding: 16, fontSize: 12, color: "var(--c-err)" }}>
          {plan.error instanceof Error ? plan.error.message : ""}
        </div>
      ) : (
        <div className="flex flex-col" style={{ gap: 12 }}>
          {outdated && <Notice text={t("dialog.outdated")} />}
          {notes.length > 0 && (
            <div className="flex flex-col" style={{ gap: 4 }}>
              <strong style={{ fontSize: 12 }}>{t("dialog.notes")}</strong>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
                {notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </div>
          )}
          {provenanceNote && <Notice text={provenanceNote} />}
          {plan.data.warnings
            .filter((w) => w.code !== "approximate_base" || !provenanceNote)
            .map((w) => (
              <Notice
                key={w.code}
                text={t(`warning.${w.code}`, { docs: w.doc_ids.join(", ") })}
              />
            ))}

          {ops.length === 0 ? (
            <p className="dim" style={{ margin: 0, fontSize: 12 }}>
              {t("dialog.nothing")}
            </p>
          ) : (
            <>
              <CountBadges
                items={countOrder(plan.data.counts).map(([action, count]) => ({
                  key: action,
                  count,
                  label: t(`count.${action}`),
                  tone: actionTone(action),
                }))}
              />
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "minmax(260px, 340px) 1fr",
                  gap: 12,
                  minHeight: 320,
                }}
              >
                <FileList>
                  {ops.map((op) => (
                    <FileRow
                      key={op.path}
                      op={op}
                      isSelected={op.path === selected}
                      resolution={resolutionOf(op)}
                      onSelect={() => {
                        setChoice({ ...current, selected: op.path });
                        setView(viewsFor(op)[0] ?? "template");
                      }}
                      onResolve={(value) => {
                        setChoice({
                          ...current,
                          resolutions: {
                            ...current.resolutions,
                            [op.path]: value,
                          },
                        });
                      }}
                    />
                  ))}
                </FileList>
                <div className="flex flex-col" style={{ gap: 8, minWidth: 0 }}>
                  {selectedOp ? (
                    <>
                      <ViewTabs
                        views={viewsFor(selectedOp).map((v) => ({
                          value: v,
                          label: t(`view.${v}`),
                        }))}
                        value={view}
                        onChange={setView}
                      />
                      <TemplateFileDiff
                        projectId={projectId}
                        path={selectedOp.path}
                        view={view}
                        toVersion={plan.data.to_version}
                        {...(selectedOp.action === "conflict"
                          ? { resolution: resolutionOf(selectedOp) }
                          : {})}
                      />
                    </>
                  ) : (
                    <div
                      className="dim flex items-center justify-center"
                      style={{ flex: 1, fontSize: 12 }}
                    >
                      {t("dialog.selectFile")}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </Modal>
  );
};

type FileRowProps = {
  op: TemplateFileOp;
  isSelected: boolean;
  resolution: ConflictResolution;
  onSelect: () => void;
  onResolve: (value: ConflictResolution) => void;
};

const FileRow = ({
  op,
  isSelected,
  resolution,
  onSelect,
  onResolve,
}: FileRowProps) => {
  const { t } = useTranslation("templateUpdate");
  return (
    <FileRowShell
      path={op.path}
      isSelected={isSelected}
      onSelect={onSelect}
      tag={
        <ActionTag
          label={t(`action.${op.action}`)}
          tone={actionTone(op.action)}
        />
      }
      trailing={
        op.approximate_base ? (
          <AlertTriangle
            size={11}
            style={{ color: "var(--c-warn)", flexShrink: 0 }}
          />
        ) : undefined
      }
    >
      {op.action === "conflict" ? (
        <Select
          value={resolution}
          onValueChange={(value) => {
            onResolve(value as ConflictResolution);
          }}
          options={op.resolutions.map((r) => ({
            value: r,
            label: t(`resolution.${r}`),
          }))}
        />
      ) : undefined}
    </FileRowShell>
  );
};
