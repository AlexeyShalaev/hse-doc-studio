import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { GitServerSource, type View } from "../ui/GitServerSource";

const entry = (id: string, title: string, view: View): GalleryEntry => ({
  id,
  title,
  frame: "page",
  width: 640,
  render: () => (
    <div style={{ padding: 24, maxWidth: 560 }}>
      <GitServerSource
        clientName="Студия на MacBook Анны"
        onPick={() => undefined}
        initialView={view}
      />
    </div>
  ),
});

/** Источник «Сервер HSE Doc Studio» в мастере клонирования (раздел 10.13), на демо-маршрутах. */
export const getGitServerGallery = (): GalleryGroup[] => [
  {
    id: "git-server",
    title: "Клонирование с сервера Студии",
    description:
      "Демо-мир: studio.example.org подключён, studio.hse.ru отозван. Вход: new.example.org одобряется через 4 с, denied.example.org отклоняется, other.example.org не Студия.",
    entries: [
      entry("servers", "Подключённые серверы", { kind: "servers" }),
      entry("login", "Вход на новый сервер", {
        kind: "login",
        url: "https://new.example.org",
      }),
      entry("projects", "Проекты сервера", {
        kind: "projects",
        credentialId: "cred_studio_ok",
      }),
      entry("revoked", "Доступ отозван", {
        kind: "projects",
        credentialId: "cred_studio_revoked",
      }),
    ],
  },
];
