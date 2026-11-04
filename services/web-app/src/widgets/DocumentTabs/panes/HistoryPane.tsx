import { useState } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAddChangelogNote, useChangelog } from "@entities/changelog";
import { Spinner } from "@shared/ui/Spinner";
import { toast, localeTag } from "@shared/lib";
import type { ChangeLogEntryResponse } from "@shared/api/types";

export type HistoryPaneProps = {
  projectId: string;
  docId: string;
};

const KIND_KEY: Record<string, string> = {
  compile_ok: "history.kind.compileOk",
  compile_fail: "history.kind.compileFail",
  edit: "history.kind.edit",
  manual_note: "history.kind.manualNote",
  sign: "history.kind.sign",
  pack_submission: "history.kind.packSubmission",
};

const formatDate = (iso: string): string => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

export const HistoryPane = ({ projectId, docId }: HistoryPaneProps) => {
  const { t } = useTranslation("documents");
  const { data, isLoading } = useChangelog(projectId, docId);
  const { mutate: addNote, isPending } = useAddChangelogNote();
  const [composing, setComposing] = useState(false);
  const [draft, setDraft] = useState("");

  const entries = data ?? [];

  const kindLabel = (kind: string): string => {
    const key = KIND_KEY[kind];
    return key ? t(key) : kind;
  };

  const summarize = (e: ChangeLogEntryResponse): string =>
    `[${kindLabel(e.kind)}] ${e.summary}`;

  const handleAdd = () => {
    if (!draft.trim()) {
      toast.error(t("history.enterDescription"));
      return;
    }
    addNote(
      {
        projectId,
        data: { doc_id: docId, summary: draft.trim() },
      },
      {
        onSuccess: () => {
          toast.success(t("history.entryAdded"));
          setDraft("");
          setComposing(false);
        },
      },
    );
  };

  return (
    <div
      className="flex flex-col"
      style={{
        padding: "1.125rem",
        gap: "0.875rem",
        flex: 1,
        minHeight: 0,
        overflowY: "auto",
      }}
    >
      <div className="flex items-center justify-between">
        <div className="flex flex-col" style={{ gap: "0.125rem" }}>
          <strong style={{ fontSize: "0.8125rem" }}>
            {t("history.title")}
          </strong>
          <span className="dim" style={{ fontSize: "0.71875rem" }}>
            {t("history.subtitle")}
          </span>
        </div>
        <button
          type="button"
          className="btn xs"
          onClick={() => {
            setComposing((v) => !v);
          }}
        >
          <Plus size="0.6875rem" />
          {t("history.newEntry")}
        </button>
      </div>

      {composing && (
        <div
          className="card"
          style={{
            padding: "0.75rem",
            gap: "0.5rem",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <textarea
            className="textarea"
            rows={3}
            value={draft}
            placeholder={t("history.draftPlaceholder")}
            onChange={(e) => {
              setDraft(e.target.value);
            }}
            disabled={isPending}
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              className="btn"
              onClick={() => {
                setComposing(false);
                setDraft("");
              }}
              disabled={isPending}
            >
              {t("history.cancel")}
            </button>
            <button
              type="button"
              className="btn primary"
              onClick={handleAdd}
              disabled={isPending}
            >
              {isPending ? <Spinner size="sm" /> : <Plus size="0.6875rem" />}
              {t("history.add")}
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div
          className="flex items-center justify-center"
          style={{ padding: "2rem" }}
        >
          <Spinner size="sm" />
        </div>
      ) : entries.length === 0 ? (
        <div
          className="dim"
          style={{
            padding: "1.5rem",
            textAlign: "center",
            fontSize: "0.75rem",
          }}
        >
          {t("history.empty")}
        </div>
      ) : (
        <div style={{ position: "relative", paddingLeft: "1rem" }}>
          <div
            style={{
              position: "absolute",
              left: "0.25rem",
              top: "0.5rem",
              bottom: "0.5rem",
              width: 1,
              background: "var(--border)",
            }}
          />
          {entries.map((e, i) => (
            <div
              key={e.id}
              className="flex flex-col"
              style={{ marginBottom: "1.125rem", position: "relative" }}
            >
              <div
                style={{
                  position: "absolute",
                  left: "-1rem",
                  top: "0.25rem",
                  width: "0.5625rem",
                  height: "0.5625rem",
                  borderRadius: "50%",
                  background: i === 0 ? "var(--accent)" : "var(--bg-2)",
                  border:
                    "1.5px solid " +
                    (i === 0 ? "var(--accent)" : "var(--border-strong)"),
                }}
              />
              <div
                className="flex items-center gap-2"
                style={{ marginBottom: "0.25rem" }}
              >
                <span
                  className="mono"
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: 600,
                    color: i === 0 ? "var(--accent)" : "var(--fg-0)",
                  }}
                >
                  {kindLabel(e.kind)}
                </span>
                <span className="mono dim" style={{ fontSize: "0.65625rem" }}>
                  {formatDate(e.at)}
                </span>
                {i === 0 && (
                  <span className="sev info" style={{ marginLeft: "0.25rem" }}>
                    HEAD
                  </span>
                )}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--fg-1)" }}>
                {summarize(e)}
              </div>
              {e.note && (
                <div
                  className="dim"
                  style={{ fontSize: "0.71875rem", marginTop: "0.125rem" }}
                >
                  {e.note}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
