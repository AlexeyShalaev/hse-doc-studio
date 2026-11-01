import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { ModelPicker, type ModelProviderGroup } from "./ModelPicker";
import { RelayErrorBlock } from "./RelayErrorBlock";

const noop = () => undefined;

const GROUPS: ModelProviderGroup[] = [
  {
    providerId: "relay",
    providerName: "Ollama на ноутбуке",
    models: ["qwen2.5:7b", "llama3.1:8b"],
    source: "own",
    unavailable: null,
  },
  {
    providerId: "own",
    providerName: "Мой OpenAI",
    models: ["gpt-4.1-mini"],
    source: "own",
    unavailable: null,
  },
  {
    providerId: "shared",
    providerName: "Общий Claude",
    models: ["claude-sonnet-4-5"],
    source: "instance",
    unavailable: null,
  },
];

const entry = (
  id: string,
  title: string,
  render: GalleryEntry["render"],
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({
  id,
  title,
  frame: "plain",
  width: 520,
  render,
  ...extra,
});

const picker = (groups: ModelProviderGroup[]) => (
  // Выбор открыт сразу: в галерее видно сам список.
  <div style={{ paddingTop: 260, display: "flex", justifyContent: "flex-end" }}>
    <ModelPicker
      groups={groups}
      selectedProviderId="relay"
      selectedModel="qwen2.5:7b"
      openRequest={1}
      onSelect={noop}
    />
  </div>
);

/** ИИ через свой раннер: выбор модели по источникам, ошибки ретрансляции, вид провайдера. */
export const getRelayGallery = (): GalleryGroup[] => [
  {
    id: "ai-relay",
    title: "ИИ через свой раннер",
    description:
      "Выбор модели по источникам (мои, организации, установки), недоступная модель раннера не в сети, ошибки ретрансляции в чате.",
    entries: [
      entry("picker_ready", "Выбор модели: раннер готов", () => picker(GROUPS)),
      entry("picker_offline", "Выбор модели: раннер не в сети", () =>
        picker(
          GROUPS.map((g) =>
            g.providerId === "relay"
              ? { ...g, unavailable: "раннер не в сети" }
              : g,
          ),
        ),
      ),
      entry("relay_unavailable", "Чат: раннер не ответил", () => (
        <RelayErrorBlock
          code="relay_unavailable"
          runnerName="MacBook Анны"
          onPickModel={noop}
        />
      )),
      entry("relay_busy", "Чат: раннер занят", () => (
        <RelayErrorBlock
          code="relay_busy"
          runnerName="MacBook Анны"
          onPickModel={noop}
        />
      )),
    ],
  },
];
