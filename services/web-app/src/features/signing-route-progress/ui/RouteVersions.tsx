import { useTranslation } from "react-i18next";
import { ExternalLink, FileText } from "lucide-react";
import { signatureDownloadUrls } from "@entities/signature";
import type { RouteDoc } from "@entities/signing-route";
import { pickLocalized } from "@shared/lib";
import { formatMoment } from "../lib/format";

export type RouteVersionsProps = {
  projectId: string;
  docs: readonly RouteDoc[];
  /** Показывать пометку «есть изменения» (только тем, кто управляет маршрутом). */
  showChanges: boolean;
};

/**
 * Документы маршрута с версией на подписи (docs/design/signing-route.md, 12.2): «Версия на
 * подписи от 10.11, 14:32» и «Открыть версию на подписи». Это `.../pdf/signed`: источник подписи
 * с видимым слоем, после фиксации сам зафиксированный PDF (12.9).
 */
export const RouteVersions = ({
  projectId,
  docs,
  showChanges,
}: RouteVersionsProps) => {
  const { t, i18n } = useTranslation("signingProgress");
  if (docs.length === 0) return null;
  return (
    <ul
      data-testid="signing-versions"
      className="flex flex-col"
      style={{ gap: "0.375rem", margin: 0, padding: 0, listStyle: "none" }}
    >
      {docs.map((doc) => {
        const name = pickLocalized(doc.name, i18n.language, doc.doc_id);
        const changed = showChanges && doc.changed;
        return (
          <li
            key={doc.doc_id}
            data-testid="signing-version"
            data-doc={doc.doc_id}
            data-changed={changed ? "true" : "false"}
            className="flex items-start"
            style={{ gap: "0.5rem", fontSize: "0.75rem", lineHeight: 1.45 }}
          >
            <FileText
              size="0.8125rem"
              aria-hidden="true"
              style={{
                flexShrink: 0,
                marginTop: "0.125rem",
                color: "var(--fg-2)",
              }}
            />
            <div
              className="flex flex-col"
              style={{ minWidth: 0, flex: 1, gap: "0.0625rem" }}
            >
              <span style={{ color: "var(--fg-0)", overflowWrap: "anywhere" }}>
                {name}
              </span>
              <span className="dim">
                {doc.sent
                  ? t("version.line", {
                      date: formatMoment(Date.parse(doc.sent.at)),
                    })
                  : t("version.none")}
                {changed && (
                  <span style={{ color: "var(--c-warn)" }}>
                    {" · "}
                    {t("version.changedTag")}
                  </span>
                )}
              </span>
              {doc.sent && (
                <a
                  href={signatureDownloadUrls.signedPdf(projectId, doc.doc_id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn xs ghost"
                  style={{ alignSelf: "flex-start", marginLeft: "-0.375rem" }}
                  data-testid="signing-version-open"
                  aria-label={t("version.openDoc", { doc: name })}
                >
                  <ExternalLink size="0.75rem" aria-hidden="true" />
                  {t("version.open")}
                </a>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
};
