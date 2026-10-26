import { useTranslation } from "react-i18next";
import type { GitContents } from "@entities/git-sync";
import { formatFileSize } from "@shared/lib";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";

export type ContentsPreviewProps = {
  contents: GitContents | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
};

const factStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  gap: 12,
  padding: "5px 0",
  borderBottom: "1px solid var(--border)",
  fontSize: 12,
};

const Fact = ({ label, value }: { label: string; value: string }) => (
  <div style={factStyle}>
    <dt className="dim">{label}</dt>
    <dd className="tnum" style={{ margin: 0, color: "var(--fg-0)" }}>
      {value}
    </dd>
  </div>
);

// Состав того, что уйдёт в репозиторий. Блокирующие находки (слишком крупные
// файлы) показаны всегда, а остальное спрятано под «Что попадёт в репозиторий»,
// чтобы шаг не превращался в простыню.
export const ContentsPreview = ({
  contents,
  isLoading,
  isError,
  onRetry,
}: ContentsPreviewProps) => {
  const { t } = useTranslation("gitRemote");

  if (isLoading) {
    return (
      <div
        className="flex items-center dim"
        role="status"
        style={{ gap: 8, fontSize: 12 }}
      >
        <Spinner size="sm" />
        {t("contents.loading")}
      </div>
    );
  }
  if (isError || !contents) {
    return (
      <Notice
        tone="warn"
        role="status"
        text={t("contents.failed")}
        action={
          <button type="button" className="btn xs" onClick={onRetry}>
            {t("contents.retry")}
          </button>
        }
      />
    );
  }

  return (
    <div className="flex flex-col" style={{ gap: 10 }}>
      {contents.over_limit.length > 0 && (
        <div data-testid="over-limit">
          <Notice
            tone="err"
            role="alert"
            text={
              <>
                <strong style={{ display: "block", fontWeight: 600 }}>
                  {t("contents.overLimit.title", {
                    count: contents.over_limit.length,
                  })}
                </strong>
                {t("contents.overLimit.text")}
                <ul
                  style={{
                    margin: "6px 0 0",
                    padding: 0,
                    listStyle: "none",
                  }}
                >
                  {contents.over_limit.map((file) => (
                    <li
                      key={file.path}
                      className="flex"
                      style={{ gap: 8, justifyContent: "space-between" }}
                    >
                      <span
                        className="mono truncate"
                        style={{ fontSize: 11.5, minWidth: 0 }}
                        title={file.path}
                      >
                        {file.path}
                      </span>
                      <span className="tnum" style={{ flexShrink: 0 }}>
                        {formatFileSize(file.bytes)}
                        {" / "}
                        {formatFileSize(file.limit)}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            }
          />
        </div>
      )}
      {contents.lfs_pointers > 0 && (
        <Notice
          tone="warn"
          role="status"
          text={t("contents.lfs", { count: contents.lfs_pointers })}
        />
      )}
      {contents.bot_authored_commits > 0 && (
        <Notice
          tone="info"
          role="status"
          text={t("contents.botAuthored", {
            count: contents.bot_authored_commits,
          })}
        />
      )}
      <details className="sync-details" data-testid="contents-details">
        <summary>{t("contents.title")}</summary>
        <div style={{ marginTop: 8 }}>
          <dl style={{ margin: 0 }}>
            <Fact
              label={t("contents.filesLabel")}
              value={t("contents.files", { count: contents.files })}
            />
            <Fact
              label={t("contents.sizeLabel")}
              value={formatFileSize(contents.bytes)}
            />
            <Fact
              label={t("contents.versionsLabel")}
              value={t("contents.versions", { count: contents.commits })}
            />
            <Fact
              label={t("contents.signaturesLabel")}
              value={String(contents.signatures)}
            />
            {contents.nda_files > 0 && (
              <Fact
                label={t("contents.ndaLabel")}
                value={String(contents.nda_files)}
              />
            )}
            <Fact
              label={t("contents.pdfLabel")}
              value={
                contents.pdf_tracked
                  ? t("contents.pdfTracked")
                  : t("contents.pdfNotTracked")
              }
            />
          </dl>
          {contents.largest.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div
                className="dim"
                style={{ fontSize: 11, marginBottom: 4, fontWeight: 600 }}
              >
                {t("contents.largest")}
              </div>
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {contents.largest.map((file) => (
                  <li
                    key={file.path}
                    className="flex"
                    style={{
                      gap: 8,
                      justifyContent: "space-between",
                      fontSize: 11.5,
                      padding: "2px 0",
                    }}
                  >
                    <span
                      className="mono truncate"
                      style={{ minWidth: 0 }}
                      title={file.path}
                    >
                      {file.path}
                    </span>
                    <span className="dim tnum" style={{ flexShrink: 0 }}>
                      {formatFileSize(file.bytes)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </details>
    </div>
  );
};
