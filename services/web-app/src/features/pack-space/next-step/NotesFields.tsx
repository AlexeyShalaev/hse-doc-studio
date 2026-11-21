import { Wand2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { PackErrorText } from "@entities/pack-studio";
import { Button, Textarea } from "@shared/ui";
import { NOTES_FIELD_ID } from "./focus";
import type { SubmitController } from "./useSubmit";

/**
 * «Что изменилось для студентов и руководителей» (pack-studio-ux.md, 5.6): заметки версии
 * ru и en, встроенные в панель вместо окна «Заметки». Пишутся сами через секунду после правки;
 * «Подсказать по изменениям» заполняет черновик по тому, что человек поправил.
 */
export const NotesFields = ({ c }: { c: SubmitController }) => {
  const { t } = useTranslation("packSpace");
  const { notes, state } = c;
  if (!state) return null;
  const disabled = c.running;
  return (
    <div className="sp-sb-block" data-testid="sp-sb-notes">
      <h3 className="sp-ch-h">{t("changes.submit.notes.title")}</h3>
      <p className="sp-ch-muted">{t("changes.submit.notes.lead")}</p>
      <div className="sp-sb-pair">
        <Textarea
          id={NOTES_FIELD_ID}
          label={t("changes.submit.notes.ru")}
          value={notes.draft.ru}
          rows={3}
          maxLength={20_000}
          disabled={disabled}
          onChange={(e) => {
            notes.set("ru", e.target.value);
          }}
          data-testid="sp-sb-notes-ru"
        />
        <Textarea
          label={t("changes.submit.notes.en")}
          value={notes.draft.en}
          rows={3}
          maxLength={20_000}
          disabled={disabled}
          onChange={(e) => {
            notes.set("en", e.target.value);
          }}
          data-testid="sp-sb-notes-en"
        />
      </div>
      {notes.breaking && (
        <div className="sp-sb-pair">
          <Textarea
            label={t("changes.submit.notes.breakingRu")}
            value={notes.draft.breakingRu}
            rows={2}
            maxLength={20_000}
            disabled={disabled}
            onChange={(e) => {
              notes.set("breakingRu", e.target.value);
            }}
          />
          <Textarea
            label={t("changes.submit.notes.breakingEn")}
            value={notes.draft.breakingEn}
            rows={2}
            maxLength={20_000}
            disabled={disabled}
            onChange={(e) => {
              notes.set("breakingEn", e.target.value);
            }}
          />
        </div>
      )}
      {notes.classNote && (
        <Textarea
          label={t("changes.submit.notes.classNote")}
          hint={t("changes.submit.notes.classNoteHint")}
          value={notes.draft.note}
          rows={2}
          maxLength={2000}
          disabled={disabled}
          onChange={(e) => {
            notes.set("note", e.target.value);
          }}
        />
      )}
      {notes.problem === "pairs" && (
        <p className="sp-sb-warn" role="status" data-testid="sp-sb-pairs">
          {t("changes.submit.notes.pairs")}
        </p>
      )}
      <div className="sp-sb-row">
        {notes.canSuggest && (
          <Button
            size="xs"
            variant="secondary"
            disabled={disabled}
            title={t("changes.submit.notes.suggestHint")}
            onClick={notes.suggest}
            data-testid="sp-sb-suggest"
          >
            <Wand2 size="0.75rem" aria-hidden="true" />
            {t("changes.submit.notes.suggest")}
          </Button>
        )}
        <span className="sp-sb-status" role="status" data-testid="sp-sb-saved">
          {notes.saving
            ? t("changes.submit.notes.saving")
            : notes.saved
              ? t("changes.submit.notes.saved")
              : notes.problem === "empty"
                ? t("changes.submit.notes.needed")
                : ""}
        </span>
      </div>
      {notes.error !== null && notes.error !== undefined && (
        <p className="sp-sb-warn" role="alert">
          <PackErrorText error={notes.error} />
        </p>
      )}
    </div>
  );
};
