import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { aiProviderApi, aiProviderKeys } from "@entities/ai-provider";
import { deviceKeys } from "@entities/connected-device";
import type { Device, DeviceEndpoint } from "@entities/connected-device";
import { toast } from "@shared/lib";

const CONNECT_TIMEOUT_S = 10;
const REQUEST_TIMEOUT_S = 60;

/**
 * «Добавить в облаке»: создаёт провайдера «через мой раннер» для модели, которую Студия открыла облаку, и подтягивает
 * список моделей через неё. Без этого шага облако знает об адресе, но чат им не пользуется.
 */
export const useAddCloudProvider = () => {
  const { t } = useTranslation("devices");
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      device,
      endpoint,
    }: {
      device: Pick<Device, "id" | "name" | "runner">;
      endpoint: Pick<DeviceEndpoint, "name">;
    }) => {
      const runner = device.runner;
      if (runner === null) throw new Error("no_runner");
      const created = await aiProviderApi.create({
        name: `${device.name}: ${endpoint.name}`,
        type: "runner",
        api_key: "",
        base_url: "",
        models: [],
        ssl_verify: true,
        connect_timeout_s: CONNECT_TIMEOUT_S,
        request_timeout_s: REQUEST_TIMEOUT_S,
        runner_id: runner.id,
        runner_endpoint: endpoint.name,
      });
      try {
        const { models } = await aiProviderApi.fetchModels(created.id);
        await aiProviderApi.update(created.id, { models });
        return { name: created.name, count: models.length };
      } catch {
        // Провайдер уже создан: модели подтянутся, когда Студия ответит, а вручную их можно загрузить в настройках.
        return { name: created.name, count: 0 };
      }
    },
    onSuccess: ({ name, count }) => {
      toast.success(
        count > 0
          ? t("ai.added", { name, count })
          : t("ai.addedNoModels", { name }),
      );
      void client.invalidateQueries({ queryKey: aiProviderKeys.all });
      void client.invalidateQueries({ queryKey: deviceKeys.all });
    },
    onError: () => {
      toast.error(t("ai.addFailed"));
    },
  });
};
