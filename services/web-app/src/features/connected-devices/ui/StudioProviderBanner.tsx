import { Bot } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  firstUnprovidedEndpoint,
  modelNames,
  useAccountDevices,
} from "@entities/connected-device";
import { useBootstrap } from "@entities/session";
import { Button } from "@shared/ui";
import { useAddCloudProvider } from "../model/useAddCloudProvider";

/**
 * Над списком провайдеров ИИ в облаке: своя Студия открыла облаку модель, а провайдера для неё нет. Это та
 * самая тихая причина «в локальной Студии разрешил, а в облаке не работает»: разрешение лишь объявляет адрес.
 */
export const StudioProviderBanner = () => {
  const { t } = useTranslation("devices");
  const mode = useBootstrap().data?.mode;
  const devices = useAccountDevices(mode === "server");
  const add = useAddCloudProvider();
  if (mode !== "server") return null;
  const found = (devices.data?.items ?? [])
    .filter((d) => d.presence === "online")
    .map((device) => ({ device, endpoint: firstUnprovidedEndpoint(device) }))
    .find((item) => item.endpoint !== null);
  if (found?.endpoint == null) return null;
  const { device, endpoint } = found;
  return (
    <div
      className="flex items-center"
      style={{
        gap: 12,
        padding: "10px 12px",
        borderRadius: 6,
        border: "1px solid var(--accent-line)",
        background: "var(--accent-soft)",
        marginBottom: 12,
      }}
      data-testid="studio-provider-banner"
    >
      <Bot size={16} style={{ color: "var(--accent)", flexShrink: 0 }} />
      <div className="flex flex-col" style={{ gap: 2, flex: 1, minWidth: 0 }}>
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>
          {t("providerBanner.title", { device: device.name })}
        </span>
        <span className="dim" style={{ fontSize: 11.5 }}>
          {endpoint.models.length > 0
            ? t("providerBanner.body", {
                models: modelNames(t, endpoint.models),
              })
            : t("providerBanner.bodyNoModels")}
        </span>
      </div>
      <Button
        variant="primary"
        size="sm"
        disabled={add.isPending}
        onClick={() => {
          add.mutate({ device, endpoint });
        }}
        data-testid="studio-provider-banner-add"
      >
        {add.isPending ? t("ai.adding") : t("ai.addInCloud")}
      </Button>
    </div>
  );
};
