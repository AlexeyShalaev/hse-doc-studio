import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FilePlus2,
  Hash,
  NotebookPen,
  PackageCheck,
  Replace,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useMovePackVersionEdits,
  usePackVersionState,
  versionDirOf,
  versionRefOf,
  type PackVersionMoved,
  type PackVersionState,
  type UpdateClass,
} from "@entities/pack-studio";
import { pickLocalized, toast } from "@shared/lib";
import { Button, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { currentClass, reasonTarget } from "../lib/versionWizard";
import type { NewVersionTarget } from "./NewVersionDialog";
import { NotesDialog } from "./NotesDialog";
import { ReleaseDialog } from "./ReleaseDialog";
import { RenumberDialog } from "./RenumberDialog";

export type VersionBarProps = {
  workspaceId: string;
  /** Пространство над git: выпуск идёт в ветке, выпущенный каталог возвращается из базы. */
  git: boolean;
  /** Открытый файл: полоса показывает версию, внутри которой он лежит. */
  path: string;
  /** Меняется с каждой сохранённой правкой: класс пересчитывается. */
  revision: number;
  onOpenFile: (path: string) => void;
  onNewVersion: (target: NewVersionTarget) => void;
  /** Шаг мастера поменял файлы на диске: редактор открывает файл заново. */
  onFilesChanged: () => void;
  /** В редакторе несохранённая правка: шаги мастера перечитают файлы, поэтому сначала сохранить. */
  editorDirty?: boolean | undefined;
};

type Dialog = "notes" | "renumber" | "release" | "move";

const TONE: Record<UpdateClass, string> = {
  patch: "ok",
  minor: "info",
  major: "warn",
};

/** Тот же файл в каталоге другой версии (после смены номера или переноса правок). */
const samePathIn = (path: string, from: string, to: string): string =>
  path.startsWith(`${from}/`) ? `${to}${path.slice(from.length)}` : path;

/**
 * Полоса мастера «Новая версия» над редактором (template-studio.md, раздел 7):
 * у черновика живой класс по классификатору с причинами, номер, заметки и
 * «Выпустить»; у выпущенной версии «Новая версия» от неё, а если её каталог
 * правили мимо Студии, «Перенести правки в новую версию» (7.3).
 */
export const VersionBar = ({
  workspaceId,
  git,
  path,
  revision,
  onOpenFile,
  onNewVersion,
  onFilesChanged,
  editorDirty = false,
}: VersionBarProps) => {
  const { t, i18n } = useTranslation("packStudio");
  const ref = versionRefOf(path);
  const versionDir = versionDirOf(path);
  const state = usePackVersionState(workspaceId, ref, String(revision));
  const move = useMovePackVersionEdits(workspaceId);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [reasonsOpen, setReasonsOpen] = useState(false);
  const close = () => {
    setDialog(null);
  };

  if (ref === null || versionDir === null) return null;
  if (state.isPending) {
    return (
      <div className="ps-version-bar" data-testid="version-bar">
        <Spinner size="sm" />
      </div>
    );
  }
  if (state.isError) {
    return (
      <div className="ps-version-bar" data-testid="version-bar">
        <Notice tone="err" role="alert" text={packErrorText(state.error)} />
      </div>
    );
  }

  const s: PackVersionState = state.data;

  const moved = (result: PackVersionMoved) => {
    close();
    onFilesChanged();
    onOpenFile(samePathIn(path, versionDir, result.version.path));
  };

  if (s.released) {
    return (
      <div className="ps-version-bar" data-testid="version-bar">
        {s.modified ? (
          <Notice
            tone="warn"
            role="status"
            text={t("version.bar.modified")}
            action={
              <Button
                size="xs"
                variant="secondary"
                onClick={() => {
                  setDialog("move");
                }}
                disabled={editorDirty}
                title={editorDirty ? t("version.bar.saveFirst") : undefined}
                data-testid="version-move-open"
              >
                <Replace size="0.6875rem" />
                {t("version.move.button")}
              </Button>
            }
          />
        ) : (
          <>
            <span className="ps-version-text">
              {t("version.bar.released", { version: s.version.version })}
            </span>
            <Button
              size="xs"
              variant="secondary"
              onClick={() => {
                onNewVersion({
                  pack: ref.pack,
                  template: ref.template,
                  base: ref.version,
                });
              }}
              data-testid="version-new-from"
            >
              <FilePlus2 size="0.6875rem" />
              {t("version.bar.newFrom")}
            </Button>
          </>
        )}
        <Modal
          isOpen={dialog === "move"}
          onClose={() => {
            if (!move.isPending) {
              move.reset();
              close();
            }
          }}
          title={t("version.move.title", { version: s.version.version })}
          description={t(git ? "version.move.leadGit" : "version.move.lead", {
            version: s.move_to ?? "",
          })}
          width={520}
          footer={
            <>
              <Button variant="secondary" onClick={close}>
                {t("common.cancel")}
              </Button>
              <Button
                disabled={move.isPending}
                onClick={() => {
                  move.mutate(
                    { ref: s.version, version: s.move_to },
                    {
                      onSuccess: (result) => {
                        toast.success(
                          t("version.move.done", {
                            version: result.version.version,
                          }),
                        );
                        if (!result.restored) {
                          toast.info(t("version.move.notRestored"));
                        }
                        move.reset();
                        close();
                        onFilesChanged();
                        onOpenFile(`${result.version.path}/version.yaml`);
                      },
                    },
                  );
                }}
                data-testid="version-move-submit"
              >
                {move.isPending ? <Spinner size="sm" /> : null}
                {t("version.move.submit", { version: s.move_to ?? "" })}
              </Button>
            </>
          }
        >
          {move.isError ? (
            <Notice tone="err" role="alert" text={packErrorText(move.error)} />
          ) : null}
        </Modal>
      </div>
    );
  }

  const cls = currentClass(s);
  const headline = pickLocalized(s.headline, i18n.language, "");
  const tone = s.suggested ? TONE[s.suggested] : "neutral";

  return (
    <div className="ps-version-bar" data-testid="version-bar">
      <div className="ps-version-info">
        <button
          type="button"
          className={`ps-version-class ps-mark-${tone}`}
          onClick={() => {
            setReasonsOpen((open) => !open);
          }}
          aria-expanded={reasonsOpen}
          disabled={s.reasons.length === 0}
          title={t("version.bar.reasons")}
          data-testid="version-class"
        >
          {s.reasons.length > 0 &&
            (reasonsOpen ? (
              <ChevronDown size="0.6875rem" aria-hidden="true" />
            ) : (
              <ChevronRight size="0.6875rem" aria-hidden="true" />
            ))}
          <span className="truncate">
            {s.base === null
              ? t("version.bar.first")
              : headline || t("version.bar.noChanges")}
          </span>
        </button>
        <span className="ps-git-chip mono" data-testid="version-number">
          <Hash size="0.6875rem" aria-hidden="true" />
          {s.version.version}
          {cls && <span>· {t(`version.class.${cls}`)}</span>}
        </span>
        {s.registered && (
          <span
            className="ps-git-chip ps-ci-ok"
            title={t("version.bar.registeredHint")}
            data-testid="version-registered"
          >
            {t("version.bar.registered")}
          </span>
        )}
      </div>
      <div className="ps-git-actions">
        <Button
          size="xs"
          variant="ghost"
          onClick={() => {
            setDialog("renumber");
          }}
          disabled={editorDirty}
          title={editorDirty ? t("version.bar.saveFirst") : undefined}
          data-testid="version-renumber-open"
        >
          <Hash size="0.6875rem" />
          <span className="ps-hide-phone">{t("version.renumber.button")}</span>
        </Button>
        <Button
          size="xs"
          variant="secondary"
          onClick={() => {
            setDialog("notes");
          }}
          disabled={editorDirty}
          title={editorDirty ? t("version.bar.saveFirst") : undefined}
          data-testid="version-notes-open"
        >
          <NotebookPen size="0.6875rem" />
          <span className="ps-hide-phone">{t("version.notes.button")}</span>
        </Button>
        <Button
          size="xs"
          onClick={() => {
            setDialog("release");
          }}
          disabled={editorDirty}
          title={editorDirty ? t("version.bar.saveFirst") : undefined}
          data-testid="version-release-open"
        >
          <PackageCheck size="0.6875rem" />
          {s.registered
            ? t("version.release.again")
            : t("version.release.button")}
        </Button>
      </div>
      {!s.number_ok && (
        <div className="ps-git-notice">
          <Notice
            tone="err"
            role="alert"
            text={t("version.bar.numberSofter")}
            action={
              s.minimum && s.numbers[s.minimum] ? (
                <Button
                  size="xs"
                  variant="secondary"
                  onClick={() => {
                    setDialog("renumber");
                  }}
                  data-testid="version-number-fix"
                >
                  {t("version.bar.numberFix", {
                    version: s.numbers[s.minimum],
                  })}
                </Button>
              ) : undefined
            }
          />
        </div>
      )}
      {s.release_outdated && (
        <div className="ps-git-notice">
          <Notice tone="warn" role="status" text={t("version.bar.outdated")} />
        </div>
      )}
      {s.error && (
        <div className="ps-git-notice">
          <Notice tone="err" role="alert" text={s.error} />
        </div>
      )}
      {reasonsOpen && s.reasons.length > 0 && (
        <ul className="ps-version-reasons" data-testid="version-reasons">
          {s.reasons.map((reason) => (
            <li key={`${reason.code}:${reason.path}`}>
              <button
                type="button"
                className="ps-git-file"
                onClick={() => {
                  onOpenFile(reasonTarget(versionDir, reason));
                }}
              >
                <span className={`ps-mark ps-mark-${TONE[reason.minimum]}`}>
                  {reason.hard
                    ? t(`version.class.${reason.minimum}`)
                    : t("version.bar.soft", {
                        cls: t(`version.class.${reason.suggested}`),
                      })}
                </span>
                <span className="ps-git-path">
                  {pickLocalized(reason.message, i18n.language, reason.path)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <NotesDialog
        workspaceId={workspaceId}
        state={s}
        isOpen={dialog === "notes"}
        onClose={close}
        onSaved={() => {
          close();
          onFilesChanged();
        }}
      />
      <RenumberDialog
        workspaceId={workspaceId}
        state={s}
        isOpen={dialog === "renumber"}
        onClose={close}
        onMoved={moved}
      />
      <ReleaseDialog
        workspaceId={workspaceId}
        git={git}
        state={s}
        isOpen={dialog === "release"}
        onClose={close}
        onReleased={() => {
          close();
          onFilesChanged();
        }}
        onMoved={moved}
      />
    </div>
  );
};
