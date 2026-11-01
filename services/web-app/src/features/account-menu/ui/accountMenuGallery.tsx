import type { GalleryGroup } from "@shared/lib/stateGallery";
import type { SessionUser } from "@entities/session";
import { AccountMenuView } from "./AccountMenuView";

const BASE: SessionUser = {
  id: "u1",
  name: "Мария Петрова",
  email: "maria.petrova@example.org",
  avatar_initials: "МП",
  is_instance_admin: false,
  email_verified: true,
  locale: "ru",
  org_roles: [],
};

const noop = () => undefined;

const entry = (
  id: string,
  title: string,
  user: SessionUser,
  extra: { note?: string; pending?: boolean } = {},
) => ({
  id,
  title,
  ...(extra.note ? { note: extra.note } : {}),
  frame: "window" as const,
  width: 420,
  render: () => (
    <div
      style={{ minHeight: 280, display: "flex", justifyContent: "flex-end" }}
    >
      <AccountMenuView
        user={user}
        defaultOpen
        pending={extra.pending ?? false}
        onOpenSettings={noop}
        onLogout={noop}
      />
    </div>
  ),
});

/** Меню аккаунта для галереи серверных экранов (/dev/server-screens). */
export const getAccountMenuGallery = (): GalleryGroup[] => [
  {
    id: "account-menu",
    title: "Меню аккаунта",
    description: "Кнопка в заголовке, раскрытая по умолчанию.",
    entries: [
      entry("account_menu_student", "Студент", BASE),
      entry("account_menu_admin", "Администратор и организации", {
        ...BASE,
        name: "Иван Сидоров",
        avatar_initials: "ИС",
        is_instance_admin: true,
        org_roles: [
          { slug: "hse-cs", name: "ФКН ВШЭ", role: "admin" },
          { slug: "lab", name: "Лаборатория", role: "member" },
        ],
      }),
      entry(
        "account_menu_unverified",
        "Почта не подтверждена",
        { ...BASE, email_verified: false },
        { note: "Рядом с именем предупреждение." },
      ),
      entry("account_menu_pending", "Выход идёт", BASE, {
        note: "Кнопка заблокирована, пока сервер закрывает сессию.",
        pending: true,
      }),
    ],
  },
];
