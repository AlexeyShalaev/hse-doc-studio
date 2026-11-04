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
        gap: "0.75rem",
        padding: "0.625rem 0.75rem",
        borderRadius: "0.375rem",
        border: "1px solid var(--accent-line)",
        background: "var(--accent-soft)",
        marginBottom: "0.75rem",
      }}
      data-testid="studio-provider-banner"
    >
      <Bot size="1rem" style={{ color: "var(--accent)", flexShrink: 0 }} />
      <div
        className="flex flex-col"
        style={{ gap: "0.125rem", flex: 1, minWidth: 0 }}
      >
        <span style={{ fontSize: "0.78125rem", fontWeight: 600 }}>
          {t("providerBanner.title", { device: device.name })}
        </span>
        <span className="dim" style={{ fontSize: "0.71875rem" }}>
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
