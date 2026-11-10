import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { AlertTriangle, Send } from "lucide-react";
import { getDocMeta, useDocuments } from "@entities/document";
import { useSignaturePlan } from "@entities/signature";
import type { PackWarning } from "@entities/submission";
import { formatVersionAt } from "../lib/versionDate";
import { useNewVersionLink } from "../model/useNewVersionLink";

type ProjectRef = {
  id: string;
  my_role?: string | null | undefined;
};

type Lang = "ru" | "en";

/** Документ, который едет в пакет версией на подписи, хотя рабочая сборка уже другая. */
type VersionNote = {
  docId: string;
  sentAt: string;
  routeId: string | null;
  /** Имя файла в пакете: запасное имя, если документа уже нет в списке. */
  file: string | null;
};

const useDocName = (projectId: string, lang: Lang) => {
  const { data: documents } = useDocuments(projectId);
  return (note: VersionNote): string => {
    const doc = documents?.find((item) => item.id === note.docId);
    if (doc) return getDocMeta(note.docId, doc, lang).name;
    return note.file?.replace(/\.[^.]+$/, "") ?? note.docId;
  };
};

type NoteRowsProps = {
  project: ProjectRef;
  lang: Lang;
  notes: readonly VersionNote[];
  /** До сборки «попадёт», после «попала». */
  textKey: "pack.before" | "pack.after";
};

const NoteRows = ({ project, lang, notes, textKey }: NoteRowsProps) => {
  const { t } = useTranslation("signingVersion");
  const docName = useDocName(project.id, lang);
  const newVersionLink = useNewVersionLink(project);
  return (
    <>
      {notes.map((note) => {
        const link = newVersionLink(note.routeId);
        return (
          <div
            key={note.docId}
            className="flex items-start gap-2"
            style={{ fontSize: "0.75rem" }}
            data-testid={`pack-version-note-${note.docId}`}
          >
            <AlertTriangle
              size={12}
              aria-hidden="true"
              style={{
                color: "var(--c-warn)",
                flexShrink: 0,
                marginTop: "0.1875rem",
              }}
            />
            <span
              className="flex flex-col"
              style={{ gap: "0.25rem", minWidth: 0 }}
            >
              <span style={{ color: "var(--fg-1)" }}>
                {t(textKey, {
                  name: docName(note),
                  date: formatVersionAt(note.sentAt),
                })}
              </span>
              {link !== null && (
                <Link
                  to={link}
                  className="btn xs"
                  style={{ alignSelf: "flex-start" }}
                  title={t("pack.sendNewVersionHint")}
                  data-testid={`pack-version-send-${note.docId}`}
                >
                  <Send size="0.6875rem" aria-hidden="true" />
                  {t("pack.sendNewVersion")}
                </Link>
              )}
            </span>
          </div>
        );
      })}
    </>
  );
};

export type PackVersionPreflightProps = {
  project: ProjectRef;
  lang: Lang;
  profileId: string;
  /** Автор пакета в команде; null у одиночного проекта. */
  author: string | null;
};

/**
 * Строки проверки перед сборкой пакета (docs/design/signing-route.md, 12.8): документ поедет
 * версией на подписи, хотя после отправки его пересобрали. Берёт то же из плана подписей точки
 * (`DocPlan.pinned`, `working_differs`), что сервер потом вернёт предупреждением
 * `changed_after_sent`. Сборку не запрещает.
 */
export const PackVersionPreflight = ({
  project,
  lang,
  profileId,
  author,
}: PackVersionPreflightProps) => {
  const { data: plan } = useSignaturePlan(project.id, profileId, author);
  const notes = (plan?.docs ?? []).flatMap((doc): VersionNote[] =>
    doc.pinned !== null && doc.working_differs
      ? [
          {
            docId: doc.doc_id,
            sentAt: doc.pinned.pinned_at,
            routeId: doc.pinned.route_id,
            file: null,
          },
        ]
      : [],
  );
  if (notes.length === 0) return null;
  return (
    <NoteRows
      project={project}
      lang={lang}
      notes={notes}
      textKey="pack.before"
    />
  );
};

export type PackVersionWarningsProps = {
  project: ProjectRef;
  lang: Lang;
  /** Предупреждения из ответа на сборку пакета (`SubmissionRecord.warnings`). */
  warnings: readonly PackWarning[];
};

/**
 * Предупреждения собранного пакета (12.8): у `changed_after_sent` своя строка с «Отправить новую
 * версию» для того, кто управляет маршрутом; прочие коды показывают готовый текст сервера.
 */
export const PackVersionWarnings = ({
  project,
  lang,
  warnings,
}: PackVersionWarningsProps) => {
  const { t } = useTranslation("signingVersion");
  const notes = warnings.flatMap((w): VersionNote[] =>
    w.code === "changed_after_sent" && w.doc_id !== null && w.sent_at !== null
      ? [
          {
            docId: w.doc_id,
            sentAt: w.sent_at,
            routeId: w.pinned?.route_id ?? null,
            file: w.file,
          },
        ]
      : [],
  );
  const others = warnings.filter(
    (w) => w.code !== "changed_after_sent" && w.message !== "",
  );
  if (notes.length === 0 && others.length === 0) return null;
  return (
    <div
      role="status"
      className="flex flex-col gap-2"
      style={{
        paddingTop: "0.75rem",
        marginTop: "0.75rem",
        borderTop: "1px dashed var(--border)",
      }}
      data-testid="pack-version-warnings"
    >
      <strong style={{ fontSize: "0.75rem" }}>{t("pack.afterTitle")}</strong>
      <NoteRows
        project={project}
        lang={lang}
        notes={notes}
        textKey="pack.after"
      />
      {others.map((w, index) => (
        <div
          key={`${w.code}:${w.doc_id ?? ""}:${String(index)}`}
          className="flex items-start gap-2"
          style={{ fontSize: "0.75rem", color: "var(--fg-1)" }}
        >
          <AlertTriangle
            size={12}
            aria-hidden="true"
            style={{
              color: "var(--c-warn)",
              flexShrink: 0,
              marginTop: "0.1875rem",
            }}
          />
          <span>{w.message}</span>
        </div>
      ))}
    </div>
  );
};
