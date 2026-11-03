import { ExternalLink, Laptop } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import {
  localConnectUrl,
  useLocalStudioInfo,
  useLocalStudioPort,
} from "@entities/local-studio";

export type OpenInLocalStudioProps = {
  /** Проект на этом сервере; без него локальная Студия только подключится. */
  projectId?: string | null;
  /** Порт, если экран сам его спрашивает; иначе запомненный. */
  port?: number;
  primary?: boolean;
  className?: string;
};

/**
 * Кнопка «Подключить локальную Студию» или «Открыть в локальной Студии»:
 * ссылка на экран подключения Студии на этом компьютере с готовым адресом
 * сервера и проектом. Код подтверждения покажет уже локальная Студия.
 */
export const OpenInLocalStudio = ({
  projectId = null,
  port,
  primary = true,
  className,
}: OpenInLocalStudioProps) => {
  const { t } = useTranslation("localStudio");
  const info = useLocalStudioInfo();
  const [storedPort] = useLocalStudioPort();
  const server = info.data?.server_url ?? null;
  const label = projectId ? t("open.project") : t("open.connect");
  if (server === null || info.data?.git_remote_enabled === false) {
    return (
      <button
        type="button"
        className={clsx("btn", primary && "primary", className)}
        disabled
        data-testid="open-in-local-studio"
      >
        <Laptop size={13} aria-hidden="true" />
        {label}
      </button>
    );
  }
  return (
    <a
      href={localConnectUrl(port ?? storedPort, server, projectId)}
      target="_blank"
      rel="noreferrer noopener"
      className={clsx("btn", primary && "primary", className)}
      style={{ textDecoration: "none" }}
      data-testid="open-in-local-studio"
    >
      <Laptop size={13} aria-hidden="true" />
      {label}
      <ExternalLink size={11} aria-hidden="true" />
    </a>
  );
};
