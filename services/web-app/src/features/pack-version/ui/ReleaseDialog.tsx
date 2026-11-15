import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  lintFailure,
  packErrorText,
  useMovePackVersionEdits,
  useReleasePackVersion,
  type PackRelease,
  type PackVersionMoved,
  type PackVersionState,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { toast } from "@shared/lib";
import { Button, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { currentClass, needsNote } from "../lib/versionWizard";

export type ReleaseDialogProps = {
  workspaceId: string;
  /** Пространство над git: выпуск идёт в рабочей ветке и окончателен после слияния PR. */
  git: boolean;
  state: PackVersionState;
  isOpen: boolean;
  onClose: () => void;
  onReleased: (released: PackRelease) => void;
  /** Номер уже выпущен в базе: правки перенесены в следующий номер. */
  onMoved: (moved: PackVersionMoved) => void;
};

/**
 * «Выпустить» (template-studio.md, 7.1, шаг 5): `status: stable`, `released_at`
 * сегодня, `release.kind`, по галочке `default_version` шаблона и запись в
 * `releases.yaml` с дайджестом каталога. У git сначала выборка базы: если номер
 * уже выпустили там (4.3), выпуск отказан и правки предлагается перенести в
 * следующий свободный номер.
 */
export const ReleaseDialog = ({
  workspaceId,
  git,
  state,
  isOpen,
  onClose,
  onReleased,
  onMoved,
}: ReleaseDialogProps) => {
  const { t } = useTranslation("packStudio");
  const uid = useId();
  const release = useReleasePackVersion(workspaceId);
  const move = useMovePackVersionEdits(workspaceId);
  const [setDefault, setSetDefault] = useState(true);
  const cls = currentClass(state);
  const lint = release.error ? lintFailure(release.error) : null;
  const taken =
    release.error instanceof ApiError &&
    release.error.code === "version_taken" &&
    typeof release.error.data?.suggested === "string"
      ? release.error.data.suggested
      : null;
  const notesMissing =
    state.changes.ru.length === 0 || state.changes.en.length === 0;

  const close = () => {
    if (release.isPending || move.isPending) return;
    release.reset();
    move.reset();
    onClose();
  };

  const submit = () => {
    release.mutate(
      {
        ref: state.version,
        body: { kind: cls, set_default: setDefault },
      },
      {
        onSuccess: (result) => {
          toast.success(
            t(git ? "version.release.doneGit" : "version.release.done", {
              version: result.version.version,
            }),
          );
          release.reset();
          onReleased(result);
        },
      },
    );
  };

  const moveTo = (version: string) => {
    move.mutate(
      { ref: state.version, version },
      {
        onSuccess: (moved) => {
          toast.success(
            t("version.move.done", { version: moved.version.version }),
          );
          release.reset();
          move.reset();
          onMoved(moved);
        },
      },
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={t("version.release.title", { version: state.version.version })}
      description={t(git ? "version.release.leadGit" : "version.release.lead")}
      width={560}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={release.isPending || move.isPending || !state.number_ok}
            onClick={submit}
            data-testid="version-release-submit"
          >
            {release.isPending ? <Spinner size="sm" /> : null}
            {state.registered
              ? t("version.release.again")
              : t("version.release.submit")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.75rem" }}>
        <dl className="ps-version-facts">
          <dt>{t("version.release.class")}</dt>
          <dd>{cls ? t(`version.class.${cls}`) : "-"}</dd>
          <dt>{t("version.release.base")}</dt>
          <dd className="mono">{state.base ?? "-"}</dd>
          <dt>{t("version.release.notes")}</dt>
          <dd>
            {t("version.release.notesCount", {
              count: state.changes.ru.length,
            })}
          </dd>
        </dl>
        {!state.number_ok && (
          <Notice
            tone="err"
            role="alert"
            text={t("version.bar.numberSofter")}
          />
        )}
        {notesMissing && (
          <Notice
            tone="warn"
            role="status"
            text={t("version.release.noNotes")}
          />
        )}
        {needsNote(state) && !state.note && (
          <Notice
            tone="warn"
            role="status"
            text={t("version.release.noteMissing")}
          />
        )}
        <label
          htmlFor={`${uid}-default`}
          className="flex items-center"
          style={{ gap: "0.5rem", fontSize: "0.78125rem" }}
        >
          <input
            id={`${uid}-default`}
            type="checkbox"
            checked={setDefault}
            onChange={(e) => {
              setSetDefault(e.target.checked);
            }}
            style={{ accentColor: "var(--accent)" }}
            data-testid="version-release-default"
          />
          {t("version.release.setDefault")}
        </label>
        {release.isError && !lint && (
          <Notice
            tone="err"
            role="alert"
            text={
              taken
                ? t("version.release.taken", {
                    version: state.version.version,
                    suggested: taken,
                  })
                : packErrorText(release.error)
            }
            action={
              taken ? (
                <Button
                  size="xs"
                  variant="secondary"
                  disabled={move.isPending}
                  onClick={() => {
                    moveTo(taken);
                  }}
                  data-testid="version-release-move"
                >
                  {t("version.release.moveTo", { version: taken })}
                </Button>
              ) : undefined
            }
          />
        )}
        {lint && (
          <div className="flex flex-col" style={{ gap: "0.375rem" }}>
            <Notice tone="err" role="alert" text={t("version.release.lint")} />
            <ul className="ps-git-notes" data-testid="version-release-findings">
              {lint.findings.map((finding) => (
                <li key={finding.message}>{finding.message}</li>
              ))}
            </ul>
          </div>
        )}
        {move.isError && (
          <Notice tone="err" role="alert" text={packErrorText(move.error)} />
        )}
      </div>
    </Modal>
  );
};
