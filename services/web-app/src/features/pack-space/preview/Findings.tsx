import { useMemo } from "react";
import { CircleAlert, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  lintTargetOf,
  usePackFilesRevision,
  usePackLint,
} from "@entities/pack-studio";
import { findingsOfFile } from "./fileFindings";

/**
 * «Замечания к файлу · N» под предпросмотром (pack-studio-ux.md, 5.5): свёрнутый список замечаний
 * открытого файла и переход к строке. Проверка одна на всю версию (тот же запрос, что у редактора
 * «Текста»), полный список всей версии лежит во вкладке «Проверка».
 */
export const Findings = ({
  workspaceId,
  path,
  onLine,
}: {
  workspaceId: string;
  path: string;
  /** Показать строку в редакторе (и открыть «Текст», если открыто другое). */
  onLine: (line: number) => void;
}) => {
  const { t } = useTranslation("packSpace");
  const revision = usePackFilesRevision(workspaceId);
  const lint = usePackLint(workspaceId, lintTargetOf(path), String(revision));
  const list = useMemo(
    () => findingsOfFile(lint.data?.findings, path),
    [lint.data, path],
  );
  const loading = lint.data === undefined && lint.isPending;
  return (
    <details className="sp-pv-findings" open data-testid="sp-pv-findings">
      <summary>
        <span>{t("preview.findings.title")}</span>
        {lint.data ? (
          <span className="sp-pv-count" data-testid="sp-pv-findings-count">
            {list.length}
          </span>
        ) : null}
      </summary>
      {loading ? (
        <p className="sp-pv-muted">…</p>
      ) : lint.data === undefined ? (
        <p className="sp-pv-muted" role="alert">
          {t("preview.findings.failed")}
        </p>
      ) : list.length === 0 ? (
        <p className="sp-pv-muted" data-testid="sp-pv-findings-none">
          {t("preview.findings.none")}
        </p>
      ) : (
        <ul className="sp-pv-finds">
          {list.map((item, index) => {
            const Icon =
              item.severity === "error" ? CircleAlert : TriangleAlert;
            return (
              <li
                key={`${String(item.line)}:${String(index)}`}
                className="sp-pv-find"
                data-severity={item.severity}
                data-testid="sp-pv-find"
              >
                <Icon size="0.875rem" aria-hidden="true" />
                <span className="sp-pv-find-text">
                  {item.line !== null ? (
                    <button
                      type="button"
                      className="sp-pv-line"
                      data-testid="sp-pv-line"
                      onClick={() => {
                        onLine(item.line ?? 1);
                      }}
                    >
                      {t("preview.findings.line", { line: item.line })}
                    </button>
                  ) : (
                    <span className="sp-pv-line-none">
                      {t("preview.findings.whole")}
                    </span>
                  )}{" "}
                  {item.message}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </details>
  );
};
