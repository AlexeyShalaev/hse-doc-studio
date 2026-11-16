import { FileText } from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { packErrorText, packWorkspacePath } from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { EmptyState } from "@shared/ui";
import { summarize } from "../lib/summary";
import { useOutcomeModel } from "../model";
import { Notice } from "./Notice";
import {
  BranchesSection,
  ChecksSection,
  DocumentsSection,
  MetaSection,
  ParticipantsSection,
  PointsSection,
  RouteSection,
} from "./sections";

/** Причина, по которой лоадер не прочитал версию (`reason` в теле ошибки), если сервер её прислал. */
const reasonOf = (error: unknown): string | null => {
  if (!(error instanceof ApiError)) return null;
  const reason = error.data?.reason;
  return typeof reason === "string" && reason !== "" ? reason : null;
};

/**
 * Центр экрана: сводка, плашки состояний и секции результата. Само содержимое секций делают срезы
 * F3 до F5, а цепочка «адрес, запрос, отрисовка» работает уже здесь: сводка и счётчики в
 * заголовках секций берутся из ответа расчёта.
 */
export const ResultCenter = () => {
  const { t } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const { outcome, shown, workspaceId, ref, url } = model;
  const failed = outcome.isError;
  const error: unknown = failed ? outcome.error : null;
  const unreadable =
    error instanceof ApiError && error.code === "version_unreadable";
  const reason = reasonOf(error);
  const sourcePath = `${ref.pack}/templates/${ref.template}/versions/${ref.version}/version.yaml`;

  const errorActions = (
    <>
      <button
        type="button"
        className="btn sm"
        data-testid="outcome-retry"
        onClick={() => void outcome.refetch()}
      >
        {t("status.retry")}
      </button>
      {url.state.state !== "work_tree" && (
        <button
          type="button"
          className="btn sm"
          data-testid="outcome-to-work-tree"
          onClick={() => {
            url.update({ state: "work_tree" });
          }}
        >
          {t("errors.workTree")}
        </button>
      )}
      <Link
        className="btn sm"
        data-testid="outcome-open-source"
        to={packWorkspacePath(workspaceId, sourcePath)}
      >
        {unreadable ? t("errors.openSource") : t("errors.openFiles")}
      </Link>
    </>
  );
  const errorLead = reason
    ? `${packErrorText(outcome.error)} ${t("errors.reason", { reason })}`
    : packErrorText(outcome.error);

  const sum = shown ? summarize(shown) : null;
  const empty = shown?.documents.length === 0;

  return (
    <div className="po-center-body">
      <div className="po-summary" data-testid="outcome-summary">
        {sum ? (
          <p className="po-summary-text">
            {t("result.summary", {
              documents: t("result.documents", { count: sum.documentsActive }),
              signers: t("result.signers", { count: sum.signers }),
            })}
          </p>
        ) : (
          <p className="po-summary-text" data-loading="true">
            <span className="shimmer po-summary-skel" aria-hidden="true" />
          </p>
        )}
      </div>

      {failed && !shown && (
        <Notice
          tone="error"
          title={t("errors.title")}
          testId="outcome-error"
          actions={errorActions}
        >
          {errorLead}
        </Notice>
      )}
      {failed && shown && (
        <Notice
          tone="error"
          title={t("status.failed")}
          testId="outcome-error-stale"
          actions={errorActions}
        >
          {`${t("result.stale")} ${errorLead}`}
        </Notice>
      )}

      {!failed || shown ? (
        empty ? (
          <EmptyState
            framed
            icon={<FileText size="1.5rem" />}
            title={t("result.emptyTitle")}
            description={t("result.emptyLead")}
            action={
              <Link
                className="btn sm"
                data-testid="outcome-empty-action"
                to={packWorkspacePath(workspaceId, sourcePath)}
              >
                {t("result.emptyAction")}
              </Link>
            }
            testId="outcome-empty"
          />
        ) : (
          <div
            className="po-sections"
            role="group"
            aria-label={t("result.sections")}
            aria-busy={outcome.isFetching || undefined}
            data-stale={failed ? "true" : undefined}
          >
            <DocumentsSection />
            <MetaSection />
            <ParticipantsSection />
            <PointsSection />
            <RouteSection />
            <ChecksSection />
            <BranchesSection />
          </div>
        )
      ) : null}
    </div>
  );
};
