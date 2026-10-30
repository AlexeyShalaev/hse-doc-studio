import type { AIProvider } from "@entities/ai-provider";
import { endpointSlug } from "@entities/runner";
import type { CloudModelCandidate } from "../ui/RemoteRunnerView";

const PRIVATE_V4 = [
  /^10\./,
  /^127\./,
  /^192\.168\./,
  /^172\.(1[6-9]|2\d|3[01])\./,
  /^169\.254\./,
];

/** Адрес в loopback или частной сети: такие модели и стоит открывать облаку. */
export const isLocalNetworkUrl = (value: string): boolean => {
  try {
    const host = new URL(value).hostname.replace(/^\[|\]$/g, "");
    return (
      host === "localhost" ||
      host === "::1" ||
      host.endsWith(".local") ||
      host.endsWith(".lan") ||
      host.endsWith(".internal") ||
      PRIVATE_V4.some((re) => re.test(host))
    );
  } catch {
    return false;
  }
};

/**
 * Локальные провайдеры, которые Студия может открыть облаку: управляемая
 * Ollama и OpenAI-совместимые адреса в своей сети. Облачные (Anthropic,
 * OpenAI) сервер и так может позвать сам, их через раннер не возят.
 */
export const cloudCandidates = (
  providers: readonly AIProvider[],
): CloudModelCandidate[] =>
  providers
    .filter(
      (p) =>
        p.type === "ollama" ||
        (p.type === "openai_compat" && isLocalNetworkUrl(p.base_url)),
    )
    .map((p) => ({
      providerId: p.id,
      name: p.name,
      flavor: p.type === "ollama" ? "ollama" : "openai",
      url: p.base_url,
      defaultName: p.type === "ollama" ? "ollama" : endpointSlug(p.name),
    }));
