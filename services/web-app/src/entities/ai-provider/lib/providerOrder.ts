import type { AIProvider, AIProviderSource } from "../model/aiProvider.schema";

/** Откуда провайдер; старый сервер шлёт только shared. */
export const providerSource = (provider: AIProvider): AIProviderSource =>
  provider.source ?? (provider.shared === true ? "instance" : "own");

const RANK: Record<AIProviderSource, number> = { own: 0, org: 1, instance: 2 };

/** Провайдер можно звать сейчас: прямой всегда, через раннер только при готовом раннере. */
export const isProviderReady = (provider: AIProvider): boolean =>
  provider.relay == null || provider.relay.state === "ready";

/**
 * Порядок по умолчанию «свой, затем организации, затем установки»; внутри
 * источника по времени создания, как выбирает сервер без явного выбора.
 */
export const orderProviders = (
  providers: readonly AIProvider[],
): AIProvider[] =>
  [...providers].sort(
    (a, b) =>
      RANK[providerSource(a)] - RANK[providerSource(b)] ||
      a.created_at.localeCompare(b.created_at),
  );

/** Первый готовый провайдер с моделями по порядку по умолчанию. */
export const defaultProvider = (
  providers: readonly AIProvider[],
): AIProvider | null =>
  orderProviders(providers).find(
    (p) => isProviderReady(p) && p.models.length > 0,
  ) ?? null;
