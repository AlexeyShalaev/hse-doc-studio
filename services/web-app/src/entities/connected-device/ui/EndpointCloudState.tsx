import { useTranslation } from "react-i18next";
import { StatusDot } from "@shared/ui/StatusDot";
import { AI_DOT } from "../lib/deviceLib";
import type { StudioLink } from "../model/device.schema";
import { AiAdvice } from "./DeviceCard";

export type EndpointCloudStateProps = {
  /** Имя, под которым Студия открыла модель облаку. */
  name: string;
  /** Адрес дошёл до сервера (`announced` у раннера): пока нет, облако о нём не знает. */
  announced: boolean;
  link: StudioLink | undefined;
};

/**
 * Под каждой открытой облаку моделью: что про неё знает облако и что сделать, если она не работает. Показывает ту
 * самую причину «разрешил в Студии, а в облаке пусто»: чаще всего там просто нет провайдера «через мой раннер».
 */
export const EndpointCloudState = ({
  name,
  announced,
  link,
}: EndpointCloudStateProps) => {
  const { t } = useTranslation("devices");
  const device = link?.servers.find((s) => s.cloud?.device)?.cloud?.device;
  const known = device?.ai.endpoints.find((e) => e.name === name);
  const state = !announced
    ? "not_opened"
    : (known?.state ?? (device ? "not_opened" : "unknown"));
  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.125rem" }}
      data-testid={`endpoint-cloud-state-${name}`}
      data-state={state}
    >
      <StatusDot status={AI_DOT[state]} label={t(`ai.state.${state}`)} />
      <AiAdvice state={state} />
    </div>
  );
};
