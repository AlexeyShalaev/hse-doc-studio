import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { ExternalLink, FileLock2 } from "lucide-react";
import { isReadOnlyRole, useProject } from "@entities/project";
import { useBootstrap } from "@entities/session";
import {
  signatureDownloadUrls,
  useDocSignaturePlan,
  useUnpinSignedVersion,
} from "@entities/signature";
import { signingCardPath } from "@entities/signing-route";
import { toast } from "@shared/lib";
import { Modal, Notice } from "@shared/ui";
import { Spinner } from "@shared/ui/Spinner";
import { formatVersionAt, shortSha } from "../lib/versionDate";

export type SignedVersionPanelProps = {
  projectId: string;
  docId: string;
};

// Маршрут, который держит документ: идёт, остановлен, возвращён или завершён (HOLDING_STATUSES).
const SIGNING_STATUSES = new Set(["active", "paused", "returned"]);

/**
 * Версия на подписи на вкладке «Подписи» документа (docs/design/signing-route.md, 12.4 и 12.8):
 * какая версия подписывается, есть ли изменения после отправки, «Открыть версию на подписи» и
 * «Подписывать текущую сборку». Снять версию нельзя, пока документ держит маршрут (сервер отвечает
 * 409 `route_locked`): кнопка тогда выключена, и рядом написано почему. У документа без версии
 * на подписи панели нет.
 */
export const SignedVersionPanel = ({
  projectId,
  docId,
}: SignedVersionPanelProps) => {
  const { t } = useTranslation("signingVersion");
  const reasonId = useId();
  const boot = useBootstrap().data;
  const { data: project } = useProject(projectId);
  const { data: plan } = useDocSignaturePlan(projectId, docId);
  const unpin = useUnpinSignedVersion();
  const [confirming, setConfirming] = useState(false);

  const entry = plan?.docs.find((doc) => doc.doc_id === docId);
  const pinned = entry?.pinned ?? null;
  if (!entry || pinned === null) return null;

  const isLocal = boot?.mode === "local";
  const date = formatVersionAt(pinned.pinned_at);
  // Маршрут документа в плане: тот, что держит документ сейчас. Заголовок по его статусу, если
  // версию снял именно он; иначе (снят с контроля, локальная Студия) просто «Версия на подписи».
  const route = plan?.route ?? null;
  const ownRoute = route !== null && route.id === pinned.route_id;
  const title = isLocal
    ? t("tab.signingServer", { date })
    : ownRoute && SIGNING_STATUSES.has(route.status)
      ? t("tab.signing", { date })
      : ownRoute && route.status === "completed"
        ? t("tab.signed", { date })
        : t("tab.pinned", { date });
  // Право записи файлов документа: у читателя и рецензента кнопки нет.
  const canWrite = !isReadOnlyRole(project?.my_role);
  const heldReason =
    route === null
      ? null
      : route.status === "completed"
        ? t("tab.heldCompleted")
        : t("tab.heldActive");

  const onUnpin = () => {
    unpin.mutate(
      { projectId, docId },
      {
        onSuccess: () => {
          setConfirming(false);
          toast.success(t("tab.done"));
        },
        onError: (err) => {
          toast.error(t("tab.failed", { reason: err.message }));
        },
      },
    );
  };

  return (
    <section
      data-testid="signed-version"
      className="flex flex-col"
      style={{
        gap: "0.5rem",
        padding: "0.75rem",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <div className="flex items-start" style={{ gap: "0.5rem" }}>
        <FileLock2
          size="0.875rem"
          aria-hidden="true"
          style={{
            color: "var(--accent)",
            flexShrink: 0,
            marginTop: "0.125rem",
          }}
        />
        <div className="flex flex-col min-w-0" style={{ gap: "0.125rem" }}>
          <strong
            style={{ fontSize: "0.78125rem", lineHeight: 1.4 }}
            data-testid="signed-version-title"
          >
            {title}
          </strong>
          <span
            className="mono dim truncate"
            style={{ fontSize: "0.6875rem" }}
            title={pinned.sha256}
          >
            {t("tab.sha", { sha: shortSha(pinned.sha256) })}
          </span>
        </div>
      </div>
      <span className="dim" style={{ fontSize: "0.6875rem", lineHeight: 1.5 }}>
        {t("tab.hint")}
      </span>
      {entry.working_differs && (
        <div data-testid="signed-version-differs">
          <Notice tone="warn" role="status" text={t("tab.differs", { date })} />
        </div>
      )}
      <div className="flex items-center flex-wrap" style={{ gap: "0.375rem" }}>
        <a
          className="btn xs"
          href={signatureDownloadUrls.signedPdf(projectId, docId)}
          target="_blank"
          rel="noreferrer"
          data-testid="signed-version-open"
        >
          <ExternalLink size="0.6875rem" aria-hidden="true" />
          {t("tab.open")}
        </a>
        {canWrite && (
          <button
            type="button"
            className="btn xs"
            disabled={heldReason !== null || unpin.isPending}
            aria-describedby={heldReason !== null ? reasonId : undefined}
            data-testid="signed-version-unpin"
            onClick={() => {
              setConfirming(true);
            }}
          >
            {t("tab.unpin")}
          </button>
        )}
      </div>
      {canWrite && heldReason !== null && route !== null && (
        <span
          id={reasonId}
          className="dim"
          style={{ fontSize: "0.6875rem", lineHeight: 1.5 }}
          data-testid="signed-version-held"
        >
          {heldReason}{" "}
          <Link to={signingCardPath(projectId, route.profile_id)}>
            {t("tab.openCard")}
          </Link>
        </span>
      )}
      <Modal
        isOpen={confirming}
        onClose={() => {
          setConfirming(false);
        }}
        title={t("tab.confirmTitle")}
        description={
          isLocal
            ? `${t("tab.confirmText", { date })} ${t("tab.confirmLocal")}`
            : t("tab.confirmText", { date })
        }
        footer={
          <>
            <button
              type="button"
              className="btn"
              disabled={unpin.isPending}
              onClick={() => {
                setConfirming(false);
              }}
            >
              {t("tab.confirmKeep")}
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={unpin.isPending}
              data-testid="signed-version-unpin-confirm"
              onClick={onUnpin}
            >
              {unpin.isPending && <Spinner size="sm" />}
              {t("tab.unpin")}
            </button>
          </>
        }
      />
    </section>
  );
};
