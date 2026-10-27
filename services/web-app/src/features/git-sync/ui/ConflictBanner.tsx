import { useLocation, useNavigate } from "react-router";
import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { gitConflictsPath } from "@entities/git-sync";
import { useSyncView } from "../model/useSyncView";

export type ConflictBannerProps = {
  projectId: string;
};

export type ConflictBannerViewProps = {
  open: number;
  total: number;
  onOpen: () => void;
};

/** Сама полоса: вид без запросов, чтобы показать её в тесте и в галерее состояний. */
export const ConflictBannerView = ({
  open,
  total,
  onOpen,
}: ConflictBannerViewProps) => {
  const { t } = useTranslation("gitSync");
  return (
    <div role="status" className="sync-banner" data-tone="err">
      <TriangleAlert
        size={14}
        aria-hidden="true"
        style={{ color: "var(--c-err)", flexShrink: 0, marginTop: 1 }}
      />
      <div className="flex flex-col" style={{ gap: 1, minWidth: 0, flex: 1 }}>
        <strong>{t("banner.title")}</strong>
        <span>{t("banner.text", { open, total })}</span>
      </div>
      <button type="button" className="btn sm" onClick={onOpen}>
        {t("banner.open")}
      </button>
    </div>
  );
};

/**
 * Полоса «синхронизация не завершена» под полосой доступа: на любом экране
 * проекта напоминает, что конфликты ждут решения и отправка заблокирована.
 * На самом экране конфликтов не показывается: там то же самое видно и так.
 */
export const ConflictBanner = ({ projectId }: ConflictBannerProps) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { status, ui } = useSyncView(projectId);

  const path = gitConflictsPath(projectId);
  if (ui.state !== "conflicts" || !status?.pending) return null;
  if (location.pathname.startsWith(path)) return null;

  return (
    <ConflictBannerView
      open={status.pending.files_open}
      total={status.pending.files_total}
      onOpen={() => {
        void navigate(path);
      }}
    />
  );
};
