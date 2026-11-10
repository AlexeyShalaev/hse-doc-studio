import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { ExternalLink, PenLine, TriangleAlert } from "lucide-react";
import { HelpAnchor } from "@entities/help";
import { useBootstrap } from "@entities/session";
import { signatureDownloadUrls } from "@entities/signature";
import {
  SigningRouteStatusSchema,
  routeSendKind,
  signingRouteEditorPath,
} from "@entities/signing-route";
import { formatDay } from "../lib/format";
import type { DocRouteVersion, SigningHold } from "../model/useDocSigningHold";
import { NewVersionAction } from "./NewVersionAction";

export type SigningHoldBannerProps = {
  projectId: string;
  docId: string;
  /** Документ держит идущий маршрут: подписи менять нельзя. */
  hold: SigningHold | null;
  /** Версия на подписи документа у маршрута, который его держит (в том числе завершённого). */
  version: DocRouteVersion | null;
  /** Владелец и редактор: им «Отправить новую версию». */
  canManage: boolean;
};

/**
 * Плашка редактора документа на подписании (docs/design/signing-route.md, 3.1, 12.2). Идущий
 * маршрут: шаг, какую версию подписывают и что правки в неё не попадут; подписи менять нельзя.
 * Рабочая сборка ушла от версии на подписи (у идущего, остановленного, возвращённого и
 * завершённого маршрута): «Есть изменения после отправки на подпись», «Отправить новую версию»
 * и «Открыть версию на подписи». Пока сервер не снимает версию на подписи (до R16), текст прежний:
 * правка и пересборка остановят маршрут.
 */
export const SigningHoldBanner = ({
  projectId,
  docId,
  hold,
  version,
  canManage,
}: SigningHoldBannerProps) => {
  const { t } = useTranslation("signingProgress");
  const meId = useBootstrap().data?.user?.id ?? null;
  const diverged = version?.changed === true ? version : null;
  if (hold === null && diverged === null) return null;

  const changed = diverged !== null;
  const profileId = hold?.profileId ?? version?.profileId ?? "";
  const pinnedDay =
    version?.pinnedAt == null ? null : formatDay(version.pinnedAt);
  const status = SigningRouteStatusSchema.safeParse(diverged?.status);
  const canSendNew =
    canManage &&
    diverged !== null &&
    status.success &&
    routeSendKind(status.data, [docId]) === "new_version";

  const changedText = ((): string | null => {
    if (diverged === null) return null;
    if (diverged.lost) return t("version.lost");
    if (diverged.status === "completed")
      return pinnedDay === null
        ? t("version.changedAfterSigned")
        : `${t("version.completed", { date: pinnedDay })} ${t("version.changedAfterSigned")}`;
    return pinnedDay === null
      ? t("version.changedNoDate")
      : t("version.changed", { date: pinnedDay });
  })();

  const tone = changed ? "var(--c-warn)" : "var(--c-info)";
  const Icon = changed ? TriangleAlert : PenLine;
  return (
    <div
      role="status"
      data-testid="signing-hold-banner"
      data-changed={changed ? "true" : "false"}
      className="flex items-start"
      style={{
        gap: "0.5rem",
        padding: "0.625rem 1rem",
        background: "var(--bg-1)",
        borderBottom: "1px solid var(--border)",
        borderLeft: `3px solid ${tone}`,
        fontSize: "0.75rem",
        lineHeight: 1.5,
        flexWrap: "wrap",
      }}
    >
      <Icon
        size="0.875rem"
        aria-hidden="true"
        style={{ color: tone, flexShrink: 0, marginTop: "0.125rem" }}
      />
      <div
        className="flex flex-col"
        style={{ gap: "0.125rem", minWidth: "min(16rem, 70%)", flex: 1 }}
      >
        {hold !== null && (
          <span style={{ color: "var(--fg-0)" }}>
            {pinnedDay === null
              ? t("hold.banner", {
                  step: hold.step ?? hold.total,
                  total: hold.total,
                })
              : t("hold.bannerVersion", {
                  step: hold.step ?? hold.total,
                  total: hold.total,
                  date: pinnedDay,
                })}
            {/* «?» плашки: шаг статьи о ходе подписания про правку документа на подписании. */}
            <HelpAnchor article="runbooks/signing-progress" step={4} />
          </span>
        )}
        {changedText !== null && (
          <span
            style={{ color: hold === null ? "var(--fg-0)" : "var(--c-warn)" }}
            data-testid="signing-hold-changed"
          >
            {changedText}
          </span>
        )}
        {hold !== null && <span className="dim">{t("hold.signatures")}</span>}
      </div>
      <div
        className="flex items-center"
        style={{ gap: "0.375rem", flexWrap: "wrap", flexShrink: 0 }}
      >
        {canSendNew && (
          <NewVersionAction
            projectId={projectId}
            routeId={diverged.routeId}
            editorPath={`${signingRouteEditorPath(projectId, profileId)}?route=${encodeURIComponent(diverged.routeId)}`}
            meId={meId}
            size="xs"
            primary
          />
        )}
        {diverged !== null && diverged.pinnedAt !== null && (
          <a
            href={signatureDownloadUrls.signedPdf(projectId, docId)}
            target="_blank"
            rel="noopener noreferrer"
            className="btn xs"
            data-testid="signing-hold-version"
          >
            <ExternalLink size="0.75rem" aria-hidden="true" />
            {t("version.open")}
          </a>
        )}
        <Link
          to={`/projects/${encodeURIComponent(projectId)}/submit/cp/${encodeURIComponent(profileId)}`}
          className="btn xs"
          data-testid="signing-hold-open"
        >
          {t("hold.open")}
        </Link>
      </div>
    </div>
  );
};
