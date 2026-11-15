import { useState } from "react";
import { Wand2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useSavePackVersionNotes,
  type PackVersionState,
} from "@entities/pack-studio";
import { toast } from "@shared/lib";
import { Button, Modal, Textarea } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  linesOf,
  needsNote,
  notesOf,
  notesParallel,
} from "../lib/versionWizard";

export type NotesDialogProps = {
  workspaceId: string;
  state: PackVersionState;
  isOpen: boolean;
  onClose: () => void;
  /** Заметки записаны в version.yaml: открытый файл перечитывается. */
  onSaved: () => void;
};

type Draft = {
  ru: string;
  en: string;
  breakingRu: string;
  breakingEn: string;
  note: string;
};

const fromState = (state: PackVersionState): Draft => ({
  ru: linesOf(state.changes.ru),
  en: linesOf(state.changes.en),
  breakingRu: linesOf(state.breaking_changes.ru),
  breakingEn: linesOf(state.breaking_changes.en),
  note: state.note ?? "",
});

/**
 * Заметки к версии (template-studio.md, 7.4): `changes` ru и en по пункту в
 * строке, черновик из отчёта классификатора по кнопке, `breaking_changes`, если
 * классификатор нашёл сужение, и объяснение класса `release.note`, если номер
 * мягче предложенного мягкими правилами (7.2).
 */
export const NotesDialog = ({
  workspaceId,
  state,
  isOpen,
  onClose,
  onSaved,
}: NotesDialogProps) => {
  const { t } = useTranslation("packStudio");
  const save = useSavePackVersionNotes(workspaceId);
  const [draft, setDraft] = useState<Draft>(() => fromState(state));
  const [opened, setOpened] = useState(isOpen);
  // Окно открыли заново: поля берут текущие заметки версии (состояние от пропа без эффекта).
  if (isOpen !== opened) {
    setOpened(isOpen);
    if (isOpen) setDraft(fromState(state));
  }

  const changes = notesOf(draft.ru, draft.en);
  const breaking = notesOf(draft.breakingRu, draft.breakingEn);
  const parallel = notesParallel(changes) && notesParallel(breaking);
  const hasDraft =
    state.draft_changes.ru.length > 0 || state.draft_breaking.ru.length > 0;
  const showBreaking =
    state.draft_breaking.ru.length > 0 ||
    state.breaking_changes.ru.length > 0 ||
    state.breaking_changes.en.length > 0;
  const showNote = needsNote(state) || state.note !== null;

  const set = (key: keyof Draft) => (value: string) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const fillFromReport = () => {
    setDraft((prev) => ({
      ...prev,
      ru: linesOf(state.draft_changes.ru),
      en: linesOf(state.draft_changes.en),
      breakingRu: linesOf(state.draft_breaking.ru),
      breakingEn: linesOf(state.draft_breaking.en),
    }));
  };

  const close = () => {
    if (save.isPending) return;
    save.reset();
    onClose();
  };

  const submit = () => {
    save.mutate(
      {
        ref: state.version,
        body: {
          changes,
          ...(showBreaking ? { breaking_changes: breaking } : {}),
          ...(showNote ? { note: draft.note.trim() } : {}),
        },
      },
      {
        onSuccess: () => {
          toast.success(t("version.notes.done"));
          save.reset();
          onSaved();
        },
      },
    );
  };

  const area = (key: keyof Draft, label: string, testId: string, rows = 4) => (
    <Textarea
      label={label}
      value={draft[key]}
      rows={rows}
      maxLength={20_000}
      onChange={(e) => {
        set(key)(e.target.value);
      }}
      data-testid={testId}
    />
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={t("version.notes.title", { version: state.version.version })}
      description={t("version.notes.lead")}
      width={680}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={save.isPending || !parallel}
            onClick={submit}
            data-testid="version-notes-save"
          >
            {t("version.notes.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.75rem" }}>
        {hasDraft && (
          <div className="ps-version-draft">
            <span className="ps-dialog-text">
              {t("version.notes.draftLead")}
            </span>
            <Button
              size="xs"
              variant="secondary"
              onClick={fillFromReport}
              data-testid="version-notes-fill"
            >
              <Wand2 size="0.6875rem" />
              {t("version.notes.fill")}
            </Button>
          </div>
        )}
        <div className="ps-version-pair">
          {area("ru", t("version.notes.changesRu"), "version-notes-ru")}
          {area("en", t("version.notes.changesEn"), "version-notes-en")}
        </div>
        {showBreaking && (
          <div className="ps-version-pair">
            {area(
              "breakingRu",
              t("version.notes.breakingRu"),
              "version-breaking-ru",
              3,
            )}
            {area(
              "breakingEn",
              t("version.notes.breakingEn"),
              "version-breaking-en",
              3,
            )}
          </div>
        )}
        {!parallel && (
          <Notice
            tone="warn"
            role="status"
            text={t("version.notes.parallel")}
          />
        )}
        {showNote && (
          <Textarea
            label={t("version.notes.note")}
            hint={t("version.notes.noteHint")}
            value={draft.note}
            rows={2}
            maxLength={2000}
            onChange={(e) => {
              set("note")(e.target.value);
            }}
            data-testid="version-notes-note"
          />
        )}
        <p className="ps-dialog-text">{t("version.notes.aiHint")}</p>
        {save.isError && (
          <Notice tone="err" role="alert" text={packErrorText(save.error)} />
        )}
      </div>
    </Modal>
  );
};
