import { Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  DeviceCard,
  type DeviceEndpoint,
  type ProjectStudios,
} from "@entities/connected-device";

export type CloudStudiosPanelProps = {
  studios: ProjectStudios;
  now: number;
  onAddProvider: (deviceId: string, endpoint: DeviceEndpoint) => void;
  addingDeviceId?: string | null;
};

/**
 * Панель облака: свои Студии проекта целиком, чужие участники одной строкой «работает локально». Деталей чужих
 * машин сервер не отдаёт, и панель не пытается их показать.
 */
export const CloudStudiosPanel = ({
  studios,
  now,
  onAddProvider,
  addingDeviceId = null,
}: CloudStudiosPanelProps) => {
  const { t } = useTranslation("devices");
  return (
    <div
      className="flex flex-col"
      style={{ gap: 10, padding: 12, maxHeight: "70vh", overflowY: "auto" }}
      data-testid="cloud-studios-panel"
    >
      <span style={{ fontSize: 12.5, fontWeight: 600 }}>
        {t("badge.title")}
      </span>
      {studios.mine.length > 0 && (
        <>
          <span className="dim" style={{ fontSize: 11 }}>
            {t("panel.mine")}
          </span>
          {studios.mine.map((device) => (
            <DeviceCard
              key={device.id}
              device={device}
              now={now}
              adding={addingDeviceId === device.id}
              onAddProvider={(endpoint) => {
                onAddProvider(device.id, endpoint);
              }}
            />
          ))}
        </>
      )}
      {studios.others.length > 0 && (
        <div
          className="flex flex-col"
          style={{ gap: 6 }}
          data-testid="studios-others"
        >
          <span className="dim" style={{ fontSize: 11 }}>
            {t("panel.others")}
          </span>
          {studios.others.map((person) => (
            <div
              key={person.user_id}
              className="flex items-center"
              style={{ gap: 8, fontSize: 12.5 }}
              data-testid="studio-other"
            >
              <Users size={13} style={{ color: "var(--fg-2)" }} />
              {t("panel.workingLocally", { name: person.name })}
            </div>
          ))}
          <span className="dim" style={{ fontSize: 11, lineHeight: 1.4 }}>
            {t("panel.othersNote")}
          </span>
        </div>
      )}
    </div>
  );
};
