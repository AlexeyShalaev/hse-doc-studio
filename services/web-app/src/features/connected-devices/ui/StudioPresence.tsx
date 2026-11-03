import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useProjectStudios,
  useStudioLink,
  type DeviceEndpoint,
} from "@entities/connected-device";
import { useBootstrap } from "@entities/session";
import { Popover, PopoverContent } from "@shared/ui/Popover";
import { useAddCloudProvider } from "../model/useAddCloudProvider";
import { cloudSummary, localSummary } from "../model/summary";
import { CloudStudiosPanel } from "./CloudStudiosPanel";
import { LocalLinkPanel } from "./LocalLinkPanel";
import { PresenceButton } from "./PresenceButton";

export type StudioPresenceProps = {
  projectId: string;
};

const NOW_TICK_MS = 30_000;

/** Часы для подписей «N минут назад»: обновляются вместе с опросом, а не каждую секунду. */
const useNow = (): number => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, NOW_TICK_MS);
    return () => {
      window.clearInterval(id);
    };
  }, []);
  return now;
};

const CloudPresence = ({ projectId }: StudioPresenceProps) => {
  const { t } = useTranslation("devices");
  const studios = useProjectStudios(projectId);
  const add = useAddCloudProvider();
  const [open, setOpen] = useState(false);
  const now = useNow();
  const summary = useMemo(
    () => cloudSummary(t, studios.data),
    [t, studios.data],
  );
  if (studios.data === undefined || summary === null) return null;
  const handleAdd = (deviceId: string, endpoint: DeviceEndpoint) => {
    const device = studios.data.mine.find((d) => d.id === deviceId);
    if (device !== undefined) add.mutate({ device, endpoint });
  };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PresenceButton summary={summary} isOpen={open} />
      <PopoverContent width={400} aria-label={t("badge.title")}>
        <CloudStudiosPanel
          studios={studios.data}
          now={now}
          onAddProvider={handleAdd}
          addingDeviceId={add.isPending ? add.variables.device.id : null}
        />
      </PopoverContent>
    </Popover>
  );
};

const LocalPresence = ({ projectId }: StudioPresenceProps) => {
  const { t } = useTranslation("devices");
  const link = useStudioLink(projectId);
  const [open, setOpen] = useState(false);
  const now = useNow();
  const summary = useMemo(() => localSummary(t, link.data), [t, link.data]);
  if (link.data === undefined || summary === null) return null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PresenceButton summary={summary} isOpen={open} />
      <PopoverContent width={400} aria-label={t("local.title")}>
        <LocalLinkPanel link={link.data} now={now} />
      </PopoverContent>
    </Popover>
  );
};

/**
 * Плашка присутствия в заголовке окна проекта: в облаке показывает подключённые Студии, в локальной Студии
 * состояние связи с облаком. Режим выбирает сервер ответом bootstrap; пока он не пришёл или показывать нечего,
 * плашки нет, и заголовок не прыгает.
 */
export const StudioPresence = ({ projectId }: StudioPresenceProps) => {
  const mode = useBootstrap().data?.mode;
  if (mode === "server") return <CloudPresence projectId={projectId} />;
  if (mode === "local") return <LocalPresence projectId={projectId} />;
  return null;
};
