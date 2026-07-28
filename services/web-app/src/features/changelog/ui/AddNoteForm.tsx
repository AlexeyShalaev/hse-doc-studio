import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAddChangelogNote } from "@entities/changelog";
import { Button } from "@shared/ui/Button";
import { Spinner } from "@shared/ui/Spinner";

type AddNoteFormProps = {
  projectId: string;
  docId?: string;
};

export const AddNoteForm = ({ projectId, docId }: AddNoteFormProps) => {
  const { t } = useTranslation("changelog");
  const { mutateAsync: addNote, isPending } = useAddChangelogNote();
  const [summary, setSummary] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!summary.trim()) return;

    await addNote({
      projectId,
      data: { summary: summary.trim(), doc_id: docId ?? null },
    });
    setSummary("");
  };

  return (
    <form
      onSubmit={(e) => void handleSubmit(e)}
      className="flex gap-2 items-end"
    >
      <input
        type="text"
        className="input flex-1"
        placeholder={t("addNote.placeholder")}
        value={summary}
        onChange={(e) => {
          setSummary(e.target.value);
        }}
        disabled={isPending}
      />
      <Button
        type="submit"
        variant="primary"
        size="sm"
        disabled={isPending || !summary.trim()}
      >
        {isPending ? <Spinner size="sm" /> : null}
        {t("addNote.submit")}
      </Button>
    </form>
  );
};
