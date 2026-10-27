import type { GalleryGroup } from "@shared/lib/stateGallery";
import { BootstrapSummary } from "./BootstrapSummary";
import { ServerUnavailable } from "./ServerUnavailable";

const LIVE: { scenario: string; title: string; note: string }[] = [
  {
    scenario: "fresh_install",
    title: "Свежая установка",
    note: "Мастер первого запуска ещё впереди: администратора нет.",
  },
  {
    scenario: "admin_ready",
    title: "Администратор",
    note: "Есть пользователь и возможность admin.",
  },
  {
    scenario: "student_ready",
    title: "Студент",
    note: "Пользователь без admin, личные ключи подписи включены.",
  },
  {
    scenario: "registration_closed",
    title: "Регистрация закрыта",
    note: "Пользователя нет, регистрация закрыта.",
  },
  {
    scenario: "sso_only",
    title: "Только SSO",
    note: "Пароли выключены, два внешних провайдера.",
  },
];

/** Состояния сессии для галереи серверных экранов (/dev/server-screens). */
export const getSessionGallery = (): GalleryGroup[] => [
  {
    id: "session-unavailable",
    title: "Сервер не ответил",
    description:
      "Вместо приложения: без bootstrap неизвестно, кто пользователь.",
    entries: [
      {
        id: "session_unavailable",
        title: "Сервер недоступен",
        frame: "window",
        width: 560,
        render: () => <ServerUnavailable onRetry={() => undefined} />,
      },
      {
        id: "session_unavailable_retrying",
        title: "Повтор идёт",
        note: "Кнопка заблокирована, пока идёт запрос.",
        frame: "window",
        width: 560,
        render: () => <ServerUnavailable onRetry={() => undefined} retrying />,
      },
    ],
  },
  {
    id: "session-bootstrap",
    title: "Состояние сессии по сценариям",
    description:
      "Ответ GET /session/bootstrap демо-мира. Открывайте по одному: сценарий меняет весь мир.",
    entries: LIVE.map((item) => ({
      id: `session_live_${item.scenario}`,
      title: item.title,
      note: item.note,
      scenario: item.scenario,
      frame: "window" as const,
      width: 560,
      render: () => <BootstrapSummary />,
    })),
  },
];
