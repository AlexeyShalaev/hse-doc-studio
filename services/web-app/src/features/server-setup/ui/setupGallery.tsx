import type { ReactNode } from "react";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import type { ServerSetupCheck, SetupSettingKey } from "@entities/session";
import type { SettingsDraft, SetupStepId } from "../lib/steps";
import { AdminStep, type AdminStepProps } from "./AdminStep";
import { DoneStep } from "./DoneStep";
import { EnvironmentStep, type EnvironmentStepProps } from "./EnvironmentStep";
import { LanguageStep } from "./LanguageStep";
import { OccupiedCard } from "./OccupiedCard";
import { RegistrationStep } from "./RegistrationStep";
import { SetupShell } from "./SetupShell";
import { SignInStep, type SignInStepProps } from "./SignInStep";

const W = 600;
const noop = () => undefined;

const entry = (
  id: string,
  title: string,
  step: SetupStepId,
  body: ReactNode,
  note?: string,
  busy = false,
): GalleryEntry => ({
  id,
  title,
  ...(note ? { note } : {}),
  frame: "window",
  width: W,
  render: () => (
    <SetupShell step={step} busy={busy}>
      {body}
    </SetupShell>
  ),
});

const admin = (props: Partial<AdminStepProps> = {}) => (
  <AdminStep
    tokenRequired
    passwordMin={10}
    onSubmit={noop}
    onBack={noop}
    onNext={noop}
    {...props}
  />
);

const DRAFT: SettingsDraft = {
  registration_mode: "invite",
  domains: "",
  require_approval: false,
  password_enabled: true,
};
const registration = (
  draft: Partial<SettingsDraft> = {},
  locked: SetupSettingKey[] = [],
) => (
  <RegistrationStep
    draft={{ ...DRAFT, ...draft }}
    locked={locked}
    onChange={noop}
    onBack={noop}
    onNext={noop}
  />
);

const signin = (props: Partial<SignInStepProps> = {}) => (
  <SignInStep
    passwordEnabled
    locked={[]}
    smtpEnabled
    onBack={noop}
    onSubmit={noop}
    {...props}
  />
);

const OK: ServerSetupCheck[] = [
  { id: "database", status: "ok", reason: null },
  { id: "storage", status: "ok", reason: null },
  { id: "runner", status: "ok", reason: null },
];
const withCheck = (
  id: ServerSetupCheck["id"],
  status: ServerSetupCheck["status"],
  reason: string | null = null,
): ServerSetupCheck[] =>
  OK.map((c) => (c.id === id ? { id, status, reason } : c));

const environment = (props: Partial<EnvironmentStepProps> = {}) => (
  <EnvironmentStep
    checks={OK}
    loading={false}
    onRecheck={noop}
    onBack={noop}
    onComplete={noop}
    {...props}
  />
);

/** Мастер первого запуска для галереи серверных экранов. */
export const getServerSetupGallery = (): GalleryGroup[] => [
  {
    id: "setup-language",
    title: "Мастер: язык и администратор",
    description:
      "Первые два шага /first-run. Токен установки нужен, пока админа нет и он не пришёл из окружения.",
    entries: [
      entry(
        "setup_language",
        "Язык",
        "language",
        <LanguageStep lang="ru" onLang={noop} onNext={noop} />,
      ),
      entry("setup_admin", "Администратор, с токеном", "admin", admin()),
      entry(
        "setup_admin_no_token",
        "Администратор, без токена",
        "admin",
        admin({ tokenRequired: false }),
        "SETUP_TOKEN_REQUIRED=false.",
      ),
      entry(
        "setup_admin_pending",
        "Создаём администратора",
        "admin",
        admin({
          pending: true,
          initial: {
            token: "st_7Fk2Rn5DxQ8WbHa1",
            name: "Иван Сидоров",
            email: "ivan.sidorov@example.org",
          },
        }),
        "",
        true,
      ),
      entry(
        "setup_admin_token_invalid",
        "Токен неверный",
        "admin",
        admin({ failure: { code: "setup_token_invalid" } }),
        "Под полем токена.",
      ),
      entry(
        "setup_admin_password_policy",
        "Пароль не подходит",
        "admin",
        admin({ failure: { code: "password_policy" } }),
        "Под полем пароля.",
      ),
      entry(
        "setup_admin_rate_limited",
        "Слишком много попыток",
        "admin",
        admin({ failure: { code: "rate_limited" } }),
      ),
      entry(
        "setup_admin_network",
        "Нет связи",
        "admin",
        admin({ failure: { code: "network" } }),
      ),
      entry(
        "setup_admin_created",
        "Администратор уже создан",
        "admin",
        admin({
          created: {
            name: "Иван Сидоров",
            email: "ivan.sidorov@example.org",
          },
        }),
        "Возврат на шаг после создания: только чтение.",
      ),
    ],
  },
  {
    id: "setup-registration",
    title: "Мастер: регистрация и входы",
    description:
      "Значения из окружения показываются только для чтения с меткой «Задано окружением».",
    entries: [
      entry(
        "setup_registration_default",
        "По приглашению (умолчание)",
        "registration",
        registration(),
      ),
      entry(
        "setup_registration_domains",
        "По доменам",
        "registration",
        registration({
          registration_mode: "domains",
          domains: "hse.ru, edu.hse.ru",
          require_approval: true,
        }),
      ),
      entry(
        "setup_registration_domains_empty",
        "По доменам, домены не указаны",
        "registration",
        registration({ registration_mode: "domains" }),
        "Дальше не пускает.",
      ),
      entry(
        "setup_registration_open",
        "Открытая",
        "registration",
        registration({ registration_mode: "open" }),
      ),
      entry(
        "setup_registration_closed",
        "Закрытая",
        "registration",
        registration({ registration_mode: "closed" }),
        "Подтверждение не нужно: аккаунты заводит админ.",
      ),
      entry(
        "setup_registration_locked_mode",
        "Режим задан окружением",
        "registration",
        registration({ registration_mode: "open" }, ["registration_mode"]),
      ),
      entry(
        "setup_registration_locked_all",
        "Всё задано окружением",
        "registration",
        registration(
          {
            registration_mode: "domains",
            domains: "hse.ru, edu.hse.ru",
            require_approval: true,
          },
          ["registration_mode", "registration_domains", "require_approval"],
        ),
      ),
      entry("setup_signin", "Входы", "signin", signin()),
      entry(
        "setup_signin_no_smtp",
        "Входы, без почты",
        "signin",
        signin({ smtpEnabled: false }),
        "Ссылки будут показываться на экране.",
      ),
      entry(
        "setup_signin_locked_password",
        "Пароль задан окружением",
        "signin",
        signin({ locked: ["password_enabled"] }),
      ),
      entry(
        "setup_signin_saving",
        "Сохраняем",
        "signin",
        signin({ pending: true }),
        "",
        true,
      ),
      entry(
        "setup_signin_failed",
        "Не сохранилось",
        "signin",
        signin({ failure: { code: "forbidden" } }),
      ),
    ],
  },
  {
    id: "setup-environment",
    title: "Мастер: проверка окружения и итог",
    description:
      "База и хранилище обязательны: красная проверка не пускает дальше. Раннеры придут позже, это предупреждение.",
    entries: [
      entry(
        "setup_env_checking",
        "Проверяем",
        "environment",
        environment({ checks: null, loading: true }),
        "",
        true,
      ),
      entry("setup_env_ok", "Всё работает", "environment", environment()),
      entry(
        "setup_env_runner_missing",
        "Раннеры не настроены",
        "environment",
        environment({ checks: withCheck("runner", "not_configured") }),
        "Предупреждение, завершить можно.",
      ),
      entry(
        "setup_env_storage_fail",
        "Хранилище не отвечает",
        "environment",
        environment({
          checks: withCheck("storage", "fail", "ClientConnectorError"),
        }),
        "Обязательная проверка красная: завершить нельзя.",
      ),
      entry(
        "setup_env_database_fail",
        "База не отвечает",
        "environment",
        environment({
          checks: withCheck("database", "fail", "OperationalError"),
        }),
      ),
      entry(
        "setup_env_load_failed",
        "Проверка не выполнилась",
        "environment",
        environment({ checks: null, loadFailed: true }),
      ),
      entry(
        "setup_env_completing",
        "Завершаем",
        "environment",
        environment({ completing: true }),
        "",
        true,
      ),
      entry(
        "setup_env_complete_failed",
        "Завершить не удалось",
        "environment",
        environment({ failure: { code: "network" } }),
      ),
      entry(
        "setup_done",
        "Готово",
        "done",
        <DoneStep smtpEnabled onOpen={noop} />,
      ),
      entry(
        "setup_done_no_smtp",
        "Готово, без почты",
        "done",
        <DoneStep smtpEnabled={false} onOpen={noop} />,
      ),
    ],
  },
  {
    id: "setup-occupied",
    title: "Мастер: нейтральный экран",
    description:
      "Проигравший гонку за первого админа и тот, у кого админ пришёл из окружения: ничего не раскрывается.",
    entries: [
      {
        id: "setup_occupied",
        title: "Не вошёл",
        note: "Под сообщением форма входа (на странице).",
        frame: "window",
        width: W,
        render: () => (
          <OccupiedCard
            signIn={
              <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
                [форма входа]
              </p>
            }
          />
        ),
      },
      {
        id: "setup_occupied_signed_in",
        title: "Вошёл не администратор",
        frame: "window",
        width: W,
        render: () => <OccupiedCard signedIn />,
      },
    ],
  },
];
