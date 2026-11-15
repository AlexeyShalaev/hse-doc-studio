import { CircleAlert, RefreshCw, TriangleAlert } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  type PackDiagnostic,
  type PackLint,
} from "@entities/pack-studio";
import { Spinner } from "@shared/ui";
import { groupFindings, relativeTo } from "../lib/findings";

export type ProblemsPanelProps = {
  path: string;
  lint: PackLint | undefined;
  loading: boolean;
  error: unknown;
  onRecheck: () => void;
  /** Перейти к находке: файл и строка (null: начало файла). */
  onOpen: (path: string, line: number | null) => void;
};

const Item = ({
  finding,
  label,
  onClick,
}: {
  finding: PackDiagnostic;
  label?: string | undefined;
  onClick?: (() => void) | undefined;
}) => {
  const { t } = useTranslation("packStudio");
  const Icon = finding.severity === "error" ? CircleAlert : TriangleAlert;
  const where = [
    label,
    finding.line !== null ? t("problems.line", { line: finding.line }) : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const body = (
    <>
      <Icon
        size="0.8125rem"
        aria-hidden="true"
        className={clsx("ps-problem-icon", `ps-problem-${finding.severity}`)}
      />
      <span className="ps-problem-text">
        <span className="ps-problem-message">{finding.message}</span>
        <span className="ps-problem-where">
          {[t(`problems.check.${finding.check}`), where]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </span>
    </>
  );
  return (
    <li data-severity={finding.severity} data-testid="problem-item">
      {onClick ? (
        <button type="button" className="ps-problem" onClick={onClick}>
          {body}
        </button>
      ) : (
        <div className="ps-problem">{body}</div>
      )}
    </li>
  );
};

/**
 * Панель «Проблемы» (template-studio.md, 5.0): находки линтера и схем версии
 * открытого файла по сохранённому состоянию. Клик ведёт к файлу и строке.
 */
export const ProblemsPanel = ({
  path,
  lint,
  loading,
  error,
  onRecheck,
  onOpen,
}: ProblemsPanelProps) => {
  const { t } = useTranslation("packStudio");
  const groups = lint ? groupFindings(lint.findings, path) : null;
  const base = lint?.scope === "version" ? lint.target : null;

  const scopeText = !lint
    ? null
    : lint.scope === "version"
      ? t("problems.scopeVersion", { version: lint.target?.split("/").pop() })
      : lint.scope === "file"
        ? t("problems.scopeFile")
        : t("problems.scopeNone");

  return (
    <div className="ps-problems" data-testid="problems-panel">
      <div className="ps-problems-head">
        <span className="ps-problems-counts" data-testid="problems-counts">
          <span className="ps-problem-error">
            <CircleAlert size="0.75rem" aria-hidden="true" />
            {t("problems.errors", { count: lint?.errors ?? 0 })}
          </span>
          <span className="ps-problem-warning">
            <TriangleAlert size="0.75rem" aria-hidden="true" />
            {t("problems.warnings", { count: lint?.warnings ?? 0 })}
          </span>
        </span>
        <button
          type="button"
          className="icon-btn"
          title={t("problems.recheck")}
          aria-label={t("problems.recheck")}
          onClick={onRecheck}
          disabled={loading}
          data-testid="problems-recheck"
        >
          {loading ? <Spinner size="sm" /> : <RefreshCw size="0.75rem" />}
        </button>
      </div>
      {scopeText && <p className="ps-problems-scope">{scopeText}</p>}
      {lint?.released && (
        <p className="ps-problems-scope">{t("problems.released")}</p>
      )}
      {error !== null && error !== undefined && (
        <p className="ps-ws-error" role="alert">
          {packErrorText(error)}
        </p>
      )}
      {lint?.findings.length === 0 && lint.scope !== "none" && (
        <p className="ps-pane-empty" data-testid="problems-clean">
          {t("problems.clean")}
        </p>
      )}
      {groups && groups.here.length > 0 && (
        <section>
          <h3 className="ps-problems-group">{t("problems.thisFile")}</h3>
          <ul className="ps-problem-list">
            {groups.here.map((finding, index) => (
              <Item
                key={`h${String(index)}`}
                finding={finding}
                onClick={() => {
                  onOpen(path, finding.line);
                }}
              />
            ))}
          </ul>
        </section>
      )}
      {groups && groups.others.length > 0 && (
        <section>
          <h3 className="ps-problems-group">{t("problems.otherFiles")}</h3>
          <ul className="ps-problem-list">
            {groups.others.flatMap(([file, list]) =>
              list.map((finding, index) => (
                <Item
                  key={`${file}:${String(index)}`}
                  finding={finding}
                  label={relativeTo(file, base)}
                  onClick={() => {
                    onOpen(file, finding.line);
                  }}
                />
              )),
            )}
          </ul>
        </section>
      )}
      {groups && groups.version.length > 0 && (
        <section>
          <h3 className="ps-problems-group">{t("problems.wholeVersion")}</h3>
          <ul className="ps-problem-list">
            {groups.version.map((finding, index) => (
              <Item key={`v${String(index)}`} finding={finding} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
};
