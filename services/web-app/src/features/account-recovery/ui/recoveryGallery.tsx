import type { GalleryGroup } from "@shared/lib/stateGallery";
import { ForgotCard, ForgotSentCard } from "./ForgotCard";
import { ResetCard, ResetDoneCard, ResetExpiredCard } from "./ResetCard";
import { ForgotForm, ResetForm, VerifyEmail } from "./containers";
import { VerifyCard, type ResendProps, type VerifyState } from "./VerifyCard";

const W = 460;
const noop = () => undefined;
const EMAIL = "anna.petrova@example.org";

const resend = (extra: Partial<ResendProps> = {}): ResendProps => ({
  smtp: true,
  onSubmit: noop,
  ...extra,
});

const verify = (state: VerifyState, extra: Partial<ResendProps> = {}) => (
  <VerifyCard state={state} resend={resend(extra)} onRetry={noop} />
);

/** «Забыл пароль», новый пароль и подтверждение почты для галереи серверных экранов. */
export const getRecoveryGallery = (): GalleryGroup[] => [
  {
    id: "forgot-states",
    title: "Забыли пароль (/forgot)",
    description:
      "Ответ всегда одинаковый: экран не выдаёт, есть ли такой адрес.",
    entries: [
      {
        id: "forgot_form",
        title: "Форма",
        frame: "window",
        width: W,
        render: () => <ForgotCard onSubmit={noop} initialEmail={EMAIL} />,
      },
      {
        id: "forgot_submitting",
        title: "Идёт отправка",
        frame: "window",
        width: W,
        render: () => (
          <ForgotCard pending onSubmit={noop} initialEmail={EMAIL} />
        ),
      },
      {
        id: "forgot_rate_limited",
        title: "Слишком много запросов",
        frame: "window",
        width: W,
        render: () => (
          <ForgotCard
            failure={{ code: "rate_limited" }}
            onSubmit={noop}
            initialEmail={EMAIL}
          />
        ),
      },
      {
        id: "forgot_network",
        title: "Нет связи",
        frame: "window",
        width: W,
        render: () => (
          <ForgotCard
            failure={{ code: "network" }}
            onSubmit={noop}
            initialEmail={EMAIL}
          />
        ),
      },
      {
        id: "forgot_sent",
        title: "Проверьте почту",
        note: "Нейтральный итог, одинаковый для любого адреса.",
        frame: "window",
        width: W,
        render: () => <ForgotSentCard email={EMAIL} link={null} smtp />,
      },
      {
        id: "forgot_sent_link",
        title: "Без почты: ссылка на экране",
        note: "LinkDelivery со ссылкой сброса.",
        frame: "window",
        width: W,
        render: () => (
          <ForgotSentCard
            email={EMAIL}
            smtp={false}
            link="https://studio.example.org/reset/rs_6Yp1Vm9GxA3JcTe0"
          />
        ),
      },
      {
        id: "forgot_sent_no_link",
        title: "Без почты, ссылки нет",
        note: "Экран не подсказывает, есть ли аккаунт: просит обратиться к администратору.",
        frame: "window",
        width: W,
        render: () => <ForgotSentCard email={EMAIL} smtp={false} link={null} />,
      },
    ],
  },
  {
    id: "reset-states",
    title: "Новый пароль (/reset/:token)",
    entries: [
      {
        id: "reset_form",
        title: "Форма",
        frame: "window",
        width: W,
        render: () => <ResetCard minLength={10} onSubmit={noop} />,
      },
      {
        id: "reset_submitting",
        title: "Идёт сохранение",
        frame: "window",
        width: W,
        render: () => <ResetCard minLength={10} pending onSubmit={noop} />,
      },
      {
        id: "reset_policy",
        title: "Пароль не подходит",
        note: "Под полем пароля.",
        frame: "window",
        width: W,
        render: () => (
          <ResetCard
            minLength={10}
            failure={{ code: "password_policy" }}
            onSubmit={noop}
          />
        ),
      },
      {
        id: "reset_network",
        title: "Нет связи",
        frame: "window",
        width: W,
        render: () => (
          <ResetCard
            minLength={10}
            failure={{ code: "network" }}
            onSubmit={noop}
          />
        ),
      },
      {
        id: "reset_done",
        title: "Пароль изменён",
        frame: "window",
        width: W,
        render: () => <ResetDoneCard />,
      },
      {
        id: "reset_expired",
        title: "Ссылка просрочена",
        note: "Путь один: запросить новую ссылку.",
        frame: "window",
        width: W,
        render: () => <ResetExpiredCard />,
      },
    ],
  },
  {
    id: "verify-states",
    title: "Подтверждение почты (/verify/:token)",
    entries: [
      {
        id: "verify_checking",
        title: "Проверяем ссылку",
        frame: "window",
        width: W,
        render: () => verify("checking"),
      },
      {
        id: "verify_done",
        title: "Почта подтверждена",
        frame: "window",
        width: W,
        render: () => verify("done"),
      },
      {
        id: "verify_invalid",
        title: "Ссылка просрочена",
        note: "С формой повторной отправки.",
        frame: "window",
        width: W,
        render: () => verify("invalid"),
      },
      {
        id: "verify_resending",
        title: "Повторная отправка идёт",
        frame: "window",
        width: W,
        render: () => verify("invalid", { pending: true }),
      },
      {
        id: "verify_resend_failed",
        title: "Повторная отправка не удалась",
        frame: "window",
        width: W,
        render: () => verify("invalid", { failure: { code: "rate_limited" } }),
      },
      {
        id: "verify_resent",
        title: "Новое письмо отправлено",
        frame: "window",
        width: W,
        render: () => verify("invalid", { sent: { email: EMAIL, link: null } }),
      },
      {
        id: "verify_resent_link",
        title: "Без почты: ссылка на экране",
        frame: "window",
        width: W,
        render: () =>
          verify("invalid", {
            smtp: false,
            sent: {
              email: EMAIL,
              link: "https://studio.example.org/verify/vf_3Hn8Zc1QwTy5LbKd",
            },
          }),
      },
      {
        id: "verify_unreachable",
        title: "Сервер не ответил",
        frame: "window",
        width: W,
        render: () => verify("unreachable"),
      },
    ],
  },
  {
    id: "recovery-live",
    title: "Ссылки из писем: живые",
    description:
      "На демо-мире. Токены со словом expired или invalid просрочены, остальные принимаются. Адрес limited@example.org даёт лимит. Слабый пароль (password…, qwerty…) отклоняется.",
    entries: [
      {
        id: "forgot_live",
        title: "Забыли пароль, письма уходят",
        scenario: "registration_open",
        frame: "window",
        width: W,
        render: () => <ForgotForm />,
      },
      {
        id: "forgot_live_nosmtp",
        title: "Забыли пароль, без почты",
        scenario: "registration_open_nosmtp",
        frame: "window",
        width: W,
        render: () => <ForgotForm />,
      },
      {
        id: "reset_live",
        title: "Новый пароль, токен rs_demo",
        scenario: "registration_open",
        frame: "window",
        width: W,
        render: () => <ResetForm token="rs_demo" />,
      },
      {
        id: "reset_live_expired",
        title: "Новый пароль, токен rs_expired",
        scenario: "registration_open",
        frame: "window",
        width: W,
        render: () => <ResetForm token="rs_expired" />,
      },
      {
        id: "verify_live",
        title: "Подтверждение, токен vf_demo",
        scenario: "registration_open",
        frame: "window",
        width: W,
        render: () => <VerifyEmail token="vf_demo" />,
      },
      {
        id: "verify_live_expired",
        title: "Подтверждение, токен vf_expired",
        note: "Просроченная ссылка с формой повторной отправки.",
        scenario: "registration_open_nosmtp",
        frame: "window",
        width: W,
        render: () => <VerifyEmail token="vf_expired" />,
      },
    ],
  },
];
