import type { GalleryGroup } from "@shared/lib/stateGallery";
import type { AuthOptions, InvitationInfo } from "@entities/session";
import { REGISTER_ERROR_CODES } from "../lib/registerErrors";
import { InviteForm } from "./InviteForm";
import { RegisterCard } from "./RegisterCard";
import { RegisterResultCard, RegisterUnavailableCard } from "./RegisterNotice";
import { SignUpForm } from "./SignUpForm";

const OPEN: AuthOptions = {
  registration_mode: "open",
  password_enabled: true,
  oidc_providers: [],
  smtp_enabled: true,
  password_min_length: 10,
};
const DOMAINS: AuthOptions = { ...OPEN, registration_mode: "domains" };
const INVITE: AuthOptions = { ...OPEN, registration_mode: "invite" };

const INVITATION: InvitationInfo = {
  email: "maria.keller@example.org",
  invited_by: "Иван Сидоров",
  org_name: "МСПИН 2025",
};

const W = 460;

const form = (
  auth: AuthOptions,
  extra: Partial<React.ComponentProps<typeof RegisterCard>> = {},
) => (
  <RegisterCard
    auth={auth}
    initialName="Maria Keller"
    initialEmail="maria.keller@example.org"
    onSubmit={() => undefined}
    {...extra}
  />
);

const failureEntry = (code: string, title: string, note?: string) => ({
  id: `register_error_${code}`,
  title,
  ...(note ? { note } : {}),
  frame: "window" as const,
  width: W,
  render: () => form(OPEN, { failure: { code } }),
});

/** Регистрация и приглашение для галереи серверных экранов. */
export const getSignUpGallery = (): GalleryGroup[] => [
  {
    id: "register-modes",
    title: "Регистрация: четыре режима",
    description: "Что видит человек на /register в каждом режиме установки.",
    entries: [
      {
        id: "register_open",
        title: "Открытая",
        note: "Любой адрес, подсказки нет.",
        frame: "window",
        width: W,
        render: () => form(OPEN),
      },
      {
        id: "register_domains",
        title: "По доменам",
        note: "Подсказка про разрешённые домены.",
        frame: "window",
        width: W,
        render: () => form(DOMAINS),
      },
      {
        id: "register_invite_required",
        title: "По приглашению, без ссылки",
        note: "Формы нет: нужна ссылка-приглашение.",
        frame: "window",
        width: W,
        render: () => <RegisterUnavailableCard reason="invite_required" />,
      },
      {
        id: "register_smtp_required",
        title: "Открытая, без почты",
        note: "Почту некому подтвердить: формы нет, нужна ссылка-приглашение.",
        frame: "window",
        width: W,
        render: () => <RegisterUnavailableCard reason="smtp_required" />,
      },
      {
        id: "register_closed",
        title: "Закрыта",
        frame: "window",
        width: W,
        render: () => <RegisterUnavailableCard reason="closed" />,
      },
      {
        id: "register_submitting",
        title: "Идёт отправка",
        frame: "window",
        width: W,
        render: () => form(OPEN, { pending: true }),
      },
      {
        id: "register_empty",
        title: "Пустая форма",
        frame: "window",
        width: W,
        render: () => form(OPEN, { initialName: "", initialEmail: "" }),
      },
    ],
  },
  {
    id: "register-invitation",
    title: "Приглашение (/invite/:token)",
    entries: [
      {
        id: "invite_org",
        title: "С организацией",
        note: "Почта подставлена и заблокирована.",
        frame: "window",
        width: W,
        render: () => form(INVITE, { invitation: INVITATION }),
      },
      {
        id: "invite_plain",
        title: "Без организации",
        frame: "window",
        width: W,
        render: () =>
          form(INVITE, { invitation: { ...INVITATION, org_name: null } }),
      },
      {
        id: "invite_invalid",
        title: "Приглашение недействительно",
        note: "Токен просрочен, отозван или не существует.",
        frame: "window",
        width: W,
        render: () => <RegisterUnavailableCard reason="invitation_invalid" />,
      },
      {
        id: "invite_unreachable",
        title: "Сервер не ответил",
        frame: "window",
        width: W,
        render: () => <RegisterUnavailableCard reason="unreachable" />,
      },
    ],
  },
  {
    id: "register-errors",
    title: "Регистрация: отказы по кодам",
    description:
      "Коды из contracts/server/error_codes.json. Домен и пароль стоят у своего поля, остальное над формой.",
    entries: [
      failureEntry(
        "domain_not_allowed",
        "Домен не разрешён",
        "Под полем почты.",
      ),
      failureEntry(
        "password_policy",
        "Пароль не подходит",
        "Под полем пароля.",
      ),
      ...REGISTER_ERROR_CODES.filter(
        (code) => code !== "domain_not_allowed" && code !== "password_policy",
      ).map((code) => failureEntry(code, code)),
      failureEntry("network", "Нет связи"),
      failureEntry("unknown", "Прочая ошибка", "Неизвестный код."),
    ],
  },
  {
    id: "register-results",
    title: "Регистрация: итоги",
    description:
      "Ответ нейтральный: «проверьте почту», без признаков, занят ли адрес.",
    entries: [
      {
        id: "result_check_email",
        title: "Проверьте почту",
        frame: "window",
        width: W,
        render: () => (
          <RegisterResultCard
            status="check_email"
            link={null}
            email="maria.keller@example.org"
          />
        ),
      },
      {
        id: "result_link_without_smtp",
        title: "Без почты: ссылка на экране",
        note: "LinkDelivery: ссылку копирует сам человек.",
        frame: "window",
        width: W,
        render: () => (
          <RegisterResultCard
            status="check_email"
            link="https://studio.example.org/verify/vf_3Hn8Zc1QwTy5LbKd"
            email="maria.keller@example.org"
          />
        ),
      },
      {
        id: "result_invited",
        title: "По приглашению на адрес",
        note: "Приглашение само подтвердило почту: письма ждать не надо.",
        frame: "window",
        width: W,
        render: () => (
          <RegisterResultCard
            status="check_email"
            link={null}
            email="maria.keller@example.org"
            invited
          />
        ),
      },
      {
        id: "result_pending_approval",
        title: "Ждёт одобрения",
        frame: "window",
        width: W,
        render: () => (
          <RegisterResultCard
            status="pending_approval"
            link={null}
            email="maria.keller@example.org"
          />
        ),
      },
    ],
  },
  {
    id: "register-live",
    title: "Регистрация: живая",
    description:
      "На демо-мире. Особые адреса: limited@example.org (лимит), approval@example.org (ждёт одобрения). В режиме доменов принимаются example.org, hse.ru, edu.hse.ru. Слабый пароль (password…, qwerty…) отклоняется. Токены приглашения: inv_demo, inv_plain (без организации), inv_expired.",
    entries: [
      {
        id: "register_live_open",
        title: "Открытая, письма уходят",
        scenario: "registration_open",
        frame: "window",
        width: W,
        render: () => <SignUpForm />,
      },
      {
        id: "register_live_domains",
        title: "По доменам",
        scenario: "registration_domains",
        frame: "window",
        width: W,
        render: () => <SignUpForm />,
      },
      {
        id: "register_live_nosmtp",
        title: "Открытая, без почты",
        note: "Почту некому подтвердить: формы нет, нужна ссылка-приглашение.",
        scenario: "registration_open_nosmtp",
        frame: "window",
        width: W,
        render: () => <SignUpForm />,
      },
      {
        id: "register_live_invite",
        title: "Приглашение inv_demo",
        scenario: "registration_open",
        frame: "window",
        width: W,
        render: () => <InviteForm token="inv_demo" />,
      },
      {
        id: "register_live_invite_expired",
        title: "Приглашение inv_expired",
        scenario: "registration_open",
        frame: "window",
        width: W,
        render: () => <InviteForm token="inv_expired" />,
      },
    ],
  },
];
