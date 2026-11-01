import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { DialogLauncher } from "@shared/ui/StateGallery";
import { AIProviderEditorModal } from "./AIProviderEditorModal";

const modal = () => (
  <DialogLauncher label="Добавить провайдера">
    {({ isOpen, close }) =>
      isOpen ? <AIProviderEditorModal isOpen onClose={close} /> : null
    }
  </DialogLauncher>
);

const entry = (
  id: string,
  title: string,
  scenario: string,
  note: string,
): GalleryEntry => ({
  id,
  title,
  note,
  frame: "window",
  width: 520,
  render: modal,
  scenario,
});

/** Провайдер «через мой раннер»: живое окно на демо-мире в разных состояниях раннеров. */
export const getAiProviderRelayGallery = (): GalleryGroup[] => [
  {
    id: "ai-provider-runner",
    title: "Провайдер через свой раннер",
    entries: [
      entry(
        "provider_runner",
        "Раннеры с ИИ-адресами",
        "runners_ready",
        "Выберите вид «Через мой раннер»: у MacBook Анны адрес ollama, у Рабочего ПК адресов нет.",
      ),
      entry(
        "provider_no_runners",
        "Раннеров нет",
        "runners_none",
        "Вид «Через мой раннер» предлагает сначала подключить раннер.",
      ),
    ],
  },
];
