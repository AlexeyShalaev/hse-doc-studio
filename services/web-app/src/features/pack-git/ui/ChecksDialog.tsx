import {
  CircleCheck,
  CircleDashed,
  CircleMinus,
  CircleX,
  ExternalLink,
  Hourglass,
  LoaderCircle,
  RefreshCw,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  usePackChecks,
  type PackCiCheck,
} from "@entities/pack-studio";
import { Button, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

const CHECK_ICON: Record<PackCiCheck["state"], LucideIcon> = {
  queued: CircleDashed,
  running: LoaderCircle,
  success: CircleCheck,
  failure: CircleX,
  neutral: CircleMinus,
  skipped: CircleMinus,
  cancelled: CircleMinus,
  awaiting_approval: Hourglass,
};

const CHECK_TONE: Record<PackCiCheck["state"], string> = {
  queued: "ps-ci-wait",
  running: "ps-ci-wait",
  success: "ps-ci-ok",
  failure: "ps-ci-err",
  neutral: "ps-ci-dim",
  skipped: "ps-ci-dim",
  cancelled: "ps-ci-dim",
  awaiting_approval: "ps-ci-wait",
};

export type ChecksDialogProps = {
  workspaceId: string;
  pushedSha: string | null;
  isOpen: boolean;
  onClose: () => void;
};

/**
 * Проверки хостинга по отправленной вершине (4.4): список с состоянием и
 * ссылками. Пока проверки идут, статус перечитывается раз в 30 секунд.
 */
export const ChecksDialog = ({
  workspaceId,
  pushedSha,
  isOpen,
  onClose,
}: ChecksDialogProps) => {
  const { t } = useTranslation("packStudio");
  const checks = usePackChecks(workspaceId, pushedSha);
  const data = checks.data;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("git.ci.title")}
      description={
        pushedSha
          ? t("git.ci.lead", { sha: pushedSha.slice(0, 7) })
          : t("git.ci.notPushed")
      }
      width={560}
      footer={
        <>
          {data?.web_url && (
            <a
              href={data.web_url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn"
              style={{ gap: "0.375rem", textDecoration: "none" }}
              data-testid="git-ci-web"
            >
              <ExternalLink size="0.75rem" aria-hidden="true" />
              {t("git.ci.web")}
            </a>
          )}
          <Button
            variant="secondary"
            disabled={checks.isFetching || pushedSha === null}
            onClick={() => void checks.refetch()}
          >
            {checks.isFetching ? (
              <Spinner size="sm" />
            ) : (
              <RefreshCw size="0.75rem" />
            )}
            {t("git.ci.refresh")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.75rem" }}>
        {checks.isError && (
          <Notice tone="err" role="alert" text={packErrorText(checks.error)} />
        )}
        {data && !data.available && (
          <Notice tone="info" role="status" text={t("git.ci.unavailable")} />
        )}
        {data?.state === "pending" && (
          <p className="ps-dialog-text">{t("git.ci.polling")}</p>
        )}
        {data?.state === "awaiting_approval" && (
          <div data-testid="git-ci-approval">
            <Notice tone="info" role="status" text={t("git.ci.approval")} />
          </div>
        )}
        {data?.available && data.checks.length === 0 && (
          <p className="ps-pane-empty" data-testid="git-ci-none">
            {t("git.ci.none")}
          </p>
        )}
        {data && data.checks.length > 0 && (
          <ul className="ps-ci-list" data-testid="git-ci-list">
            {data.checks.map((check, index) => {
              const Icon = CHECK_ICON[check.state];
              return (
                <li
                  key={`${check.name}:${String(index)}`}
                  className="ps-ci-item"
                  data-state={check.state}
                >
                  <Icon
                    size="0.875rem"
                    aria-hidden="true"
                    className={clsx("ps-ci-icon", CHECK_TONE[check.state])}
                  />
                  <span className="ps-ci-text">
                    <span className="ps-ci-name">
                      {check.url ? (
                        <a
                          href={check.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {check.name}
                        </a>
                      ) : (
                        check.name
                      )}
                    </span>
                    <span className="ps-ci-summary">
                      {[t(`git.ci.check.${check.state}`), check.summary]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Modal>
  );
};
