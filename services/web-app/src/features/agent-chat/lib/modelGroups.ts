import { isProviderReady, type AIProvider } from "@entities/ai-provider";
import type { ModelProviderGroup } from "../ui/ModelPicker";

/**
 * Группы выбора модели по провайдерам. Источник («мои, организации,
 * установки») передаётся только в серверном режиме: локальный бэкенд тоже
 * присылает source: "own", но там список остаётся прежним, без групп.
 */
export const toModelGroups = (
  providers: readonly AIProvider[],
  bySource: boolean,
  unavailableLabel: (
    state: NonNullable<AIProvider["relay"]>["state"],
  ) => string,
): ModelProviderGroup[] =>
  providers
    .map((provider) => ({
      providerId: provider.id,
      providerName: provider.name,
      models: provider.models,
      source: bySource ? provider.source : undefined,
      // Провайдер через раннер недоступен, пока раннер не готов: модели видны,
      // но выбрать их нельзя, а причина стоит вместо имени провайдера.
      unavailable:
        provider.relay && !isProviderReady(provider)
          ? unavailableLabel(provider.relay.state)
          : null,
    }))
    .filter((group) => group.models.length > 0);
