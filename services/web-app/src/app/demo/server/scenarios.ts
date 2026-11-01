import type { ServerDemoInstallSeed } from "./adminInstall";
import type {
  ServerDemoPersonalSeed,
  ServerDemoRemoteSeed,
} from "./personalRunners";
import type {
  Bootstrap,
  Capabilities,
  SessionUser,
  SetupSettingKey,
} from "@entities/session";

// Сценарии серверного демо (VITE_SERVER_DEMO=1): с каким состоянием установки и
// сессии открывается приложение. Формы совпадают с эталонами contracts/server/fixtures/Bootstrap:
// тест сверяет демо с самими файлами, так что расхождение с настоящим API видно сразу.

export type ServerDemoScenarioId =
  | "fresh_install"
  | "fresh_install_env"
  | "fresh_install_raced"
  | "fresh_install_broken"
  | "admin_ready"
  | "admin_scale"
  | "admin_env_locked"
  | "admin_sso"
  | "admin_no_orgs"
  | "ops_runners_offline"
  | "ops_services_degraded"
  | "ops_fresh"
  | "install_env_locked"
  | "install_fresh"
  | "org_admin"
  | "student_ready"
  | "registration_closed"
  | "sso_only"
  | "registration_open"
  | "registration_domains"
  | "registration_open_nosmtp"
  | "newcomer"
  | "student_nosmtp"
  | "student_sso"
  | "student_linked"
  | "runners_ready"
  | "runners_none"
  | "runners_offline"
  | "runners_disabled"
  | "admin_personal_runners"
  | "admin_runners_disabled"
  | "local_remote_off"
  | "local_remote_online"
  | "local_remote_problems"
  | "links_guest";

export const DEFAULT_SERVER_SCENARIO_ID: ServerDemoScenarioId = "student_ready";

const SERVER_CAPABILITIES: Capabilities = {
  fs_browse: false,
  connect_folder: false,
  open_in_editor: false,
  move_project: false,
  docker_ui: false,
  self_update: false,
  local_services_ui: false,
  admin: false,
  personal_signing_keys: true,
  personal_runners: false,
  remote_runner: false,
  // Сервер отдаёт проекты по git: «Клонировать с сервера» в настройках проекта.
  git_remote: true,
  git_server_login: false,
};

export const DEMO_STUDENT: SessionUser = {
  id: "u_01hx7k2m9c",
  name: "Анна Петрова",
  email: "anna.petrova@example.org",
  avatar_initials: "АП",
  is_instance_admin: false,
  email_verified: true,
  locale: "ru",
  org_roles: [{ slug: "msp-2025", name: "МСПИН 2025", role: "member" }],
};

export const DEMO_ADMIN: SessionUser = {
  id: "u_01hx7k1a0b",
  name: "Иван Сидоров",
  email: "ivan.sidorov@example.org",
  avatar_initials: "ИС",
  is_instance_admin: true,
  email_verified: true,
  locale: "en",
  org_roles: [{ slug: "msp-2025", name: "МСПИН 2025", role: "owner" }],
};

/** Админ организации: не админ установки, но управляет двумя организациями. */
export const DEMO_ORG_ADMIN: SessionUser = {
  id: "u_01hx7k3e5f",
  name: "Елена Миронова",
  email: "elena.mironova@example.org",
  avatar_initials: "ЕМ",
  is_instance_admin: false,
  email_verified: true,
  locale: "ru",
  org_roles: [
    { slug: "msp-2025", name: "МСПИН 2025", role: "admin" },
    { slug: "ai-lab", name: "Лаборатория ИИ", role: "owner" },
  ],
};

export const ORG_ADMIN_CSRF = "Zr4cNb8LkQ2wXs6YtVe0PdMh9aUfJg3o";

/** Новичок: вошёл впервые, ни проектов, ни организаций. */
export const DEMO_NEWCOMER: SessionUser = {
  id: "u_01hx7k9newcomer",
  name: "Мария Келлер",
  email: "maria.keller@example.org",
  avatar_initials: "МК",
  is_instance_admin: false,
  email_verified: true,
  locale: "ru",
  org_roles: [],
};

const GUEST_DEMO_CSRF = "Gq8vT1mZ3xK0cR7bN5yH2wLsJp9eDg6o";
const GUEST_DEMO_INFO: NonNullable<Bootstrap["guest"]> = {
  name: "Борис",
  links: [
    {
      project_id: "p_01hxa1c4de",
      project_name: "Bertie: курсовой проект",
      link_label: "Для группы",
      role: "editor",
      show_sources: true,
    },
    {
      project_id: "p_01hxa3k2jm",
      project_name: "Анализ нагрузки на очередь задач",
      link_label: "Для научрука",
      role: "reader",
      show_sources: false,
    },
  ],
};

export const STUDENT_CSRF = "Wm3x0Qk7bVfN1c8RtYhA4uLsJp2eDg6o";
export const ADMIN_CSRF = "Hq9dLz5TnXe2VwB7kYc0RmPa4sUfJg1i";

const base = (overrides: Partial<Bootstrap>): Bootstrap =>
  withPersonalRunners({
    mode: "server",
    version: "0.2.0",
    setup_state: "ready",
    auth: {
      registration_mode: "open",
      password_enabled: true,
      oidc_providers: [],
      smtp_enabled: true,
      password_min_length: 10,
    },
    user: null,
    capabilities: { ...SERVER_CAPABILITIES },
    csrf_token: null,
    guest: null,
    ...overrides,
  });

/** Свои раннеры подключает только вошедший человек (личные раннеры в демо разрешены). */
const withPersonalRunners = (boot: Bootstrap): Bootstrap => ({
  ...boot,
  capabilities: { ...boot.capabilities, personal_runners: boot.user !== null },
  // invites: счётчик «Входящих» есть только у вошедшего.
  inbox: boot.inbox ?? (boot.user ? { unread: 0 } : null),
});

/** Анна на сервере с личными раннерами (или с выключенными администратором). */
const personalBase = (enabled: boolean): Bootstrap => {
  const boot = base({
    auth: {
      registration_mode: "domains",
      password_enabled: true,
      oidc_providers: [],
      smtp_enabled: true,
      password_min_length: 10,
    },
    user: DEMO_STUDENT,
    csrf_token: STUDENT_CSRF,
  });
  // base() открывает личные раннеры любому вошедшему; выключение админом задаём поверх.
  return {
    ...boot,
    capabilities: { ...boot.capabilities, personal_runners: enabled },
  };
};

/**
 * Локальная Студия: без входа, без Docker-экранов и локальных служб (их в демо
 * нет), зато с облачными сборками на этой машине.
 */
const localBase = (): Bootstrap => ({
  mode: "local",
  version: "0.2.0",
  setup_state: "ready",
  auth: {
    registration_mode: "closed",
    password_enabled: false,
    oidc_providers: [],
    smtp_enabled: false,
    password_min_length: 10,
  },
  user: null,
  capabilities: {
    fs_browse: false,
    connect_folder: false,
    open_in_editor: false,
    move_project: false,
    docker_ui: false,
    self_update: false,
    local_services_ui: false,
    admin: false,
    personal_signing_keys: false,
    personal_runners: false,
    remote_runner: true,
    git_remote: false,
    // Локальная Студия входит на сервер Студии кодом и клонирует его проекты.
    git_server_login: true,
  },
  csrf_token: null,
  guest: null,
});

/** Токен установки демо: тот же, что в эталоне ServerSetupAdminRequest. */
export const DEMO_SETUP_TOKEN = "st_7Fk2Rn5DxQ8WbHa1";

/** Что уже есть на установке, когда открывается мастер первого запуска. */
export type ServerDemoSetup = {
  /** Администратор уже создан (окружением или другим человеком). */
  adminExists: boolean;
  /** Ключи, заданные окружением: мастер показывает их только для чтения. */
  locked: SetupSettingKey[];
  /** Хранилище файлов в проверке окружения. */
  storage: "ok" | "fail";
};

export const DEFAULT_DEMO_SETUP: ServerDemoSetup = {
  adminExists: false,
  locked: [],
  storage: "ok",
};

export type ServerDemoScenario = {
  id: ServerDemoScenarioId;
  /** Bootstrap, с которого начинается сценарий. */
  bootstrap: () => Bootstrap;
  /** Токен установки нужен для первого администратора. */
  tokenRequired: boolean;
  /** Состояние мастера первого запуска; по умолчанию чистая установка. */
  setup?: Partial<ServerDemoSetup>;
  /** Настройки входа в админке: чем они заданы. По умолчанию всё редактируется. */
  adminSeed?: ServerDemoAdminSeed;
  /** Организации в админке: набор по умолчанию или ни одной. */
  orgSeed?: "default" | "empty";
  /** Раннеры, очередь, сервисы и место в админке: набор по умолчанию или вариант состояния. */
  opsSeed?: ServerDemoOpsSeed;
  /** Название, сборка, политика ключей и общие провайдеры: набор по умолчанию или вариант состояния. */
  installSeed?: ServerDemoInstallSeed;
  /**
   * Большой мир: десятки тысяч людей, тысячи организаций, задач и записей
   * журнала (scaleWorld.ts). Чтобы оценить поиск, фильтры и листание.
   */
  scale?: boolean;
  /** Личные раннеры, сопряжение и провайдеры через раннер: набор по умолчанию или вариант. */
  personalSeed?: ServerDemoPersonalSeed;
  /** Облачные сборки локальной Студии (сценарии local_remote_*). */
  remoteSeed?: ServerDemoRemoteSeed;
};

/** default: рабочая установка; runners_offline: раннеров в сети нет; services_degraded: сервисы падают, места мало; fresh: ничего не подключено. */
export type ServerDemoOpsSeed =
  "default" | "runners_offline" | "services_degraded" | "fresh";

/** default: всё редактируется; env_locked: регистрация и почта заданы окружением; sso: пароль выключен, провайдеры включены. */
export type ServerDemoAdminSeed = "default" | "env_locked" | "sso";

export const SERVER_SCENARIOS: readonly ServerDemoScenario[] = [
  {
    id: "fresh_install",
    tokenRequired: true,
    bootstrap: () =>
      base({
        setup_state: "needs_admin",
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: false,
          password_min_length: 10,
        },
        // Политика ключей по умолчанию запрещает хранить их на сервере.
        capabilities: { ...SERVER_CAPABILITIES, personal_signing_keys: false },
      }),
  },
  {
    id: "fresh_install_env",
    tokenRequired: false,
    setup: {
      adminExists: true,
      locked: ["registration_mode", "registration_domains", "require_approval"],
    },
    bootstrap: () =>
      base({
        setup_state: "needs_admin",
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: false,
          password_min_length: 10,
        },
      }),
  },
  {
    id: "fresh_install_raced",
    tokenRequired: false,
    setup: { adminExists: true },
    bootstrap: () =>
      base({
        setup_state: "needs_admin",
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: false,
          password_min_length: 10,
        },
      }),
  },
  {
    id: "fresh_install_broken",
    tokenRequired: true,
    setup: { storage: "fail" },
    bootstrap: () =>
      base({
        setup_state: "needs_admin",
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: false,
          password_min_length: 10,
        },
      }),
  },
  {
    id: "admin_ready",
    tokenRequired: false,
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_ADMIN,
        capabilities: { ...SERVER_CAPABILITIES, admin: true },
        csrf_token: ADMIN_CSRF,
      }),
  },
  {
    id: "admin_scale",
    tokenRequired: false,
    scale: true,
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_ADMIN,
        capabilities: { ...SERVER_CAPABILITIES, admin: true },
        csrf_token: ADMIN_CSRF,
      }),
  },
  {
    id: "admin_env_locked",
    tokenRequired: false,
    adminSeed: "env_locked",
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "domains",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_ADMIN,
        capabilities: { ...SERVER_CAPABILITIES, admin: true },
        csrf_token: ADMIN_CSRF,
      }),
  },
  {
    id: "admin_sso",
    tokenRequired: false,
    adminSeed: "sso",
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "closed",
          password_enabled: false,
          oidc_providers: [
            { id: "keycloak", label: "HSE SSO" },
            { id: "google", label: "Google" },
          ],
          smtp_enabled: false,
          password_min_length: 10,
        },
        user: DEMO_ADMIN,
        capabilities: { ...SERVER_CAPABILITIES, admin: true },
        csrf_token: ADMIN_CSRF,
      }),
  },
  {
    id: "admin_no_orgs",
    tokenRequired: false,
    orgSeed: "empty",
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_ADMIN,
        capabilities: { ...SERVER_CAPABILITIES, admin: true },
        csrf_token: ADMIN_CSRF,
      }),
  },
  {
    id: "ops_runners_offline",
    tokenRequired: false,
    opsSeed: "runners_offline",
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_ADMIN,
        capabilities: { ...SERVER_CAPABILITIES, admin: true },
        csrf_token: ADMIN_CSRF,
      }),
  },
  {
    id: "ops_services_degraded",
    tokenRequired: false,
    opsSeed: "services_degraded",
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_ADMIN,
        capabilities: { ...SERVER_CAPABILITIES, admin: true },
        csrf_token: ADMIN_CSRF,
      }),
  },
  {
    id: "ops_fresh",
    tokenRequired: false,
    opsSeed: "fresh",
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: false,
          password_min_length: 10,
        },
        user: DEMO_ADMIN,
        capabilities: { ...SERVER_CAPABILITIES, admin: true },
        csrf_token: ADMIN_CSRF,
      }),
  },
  {
    id: "install_env_locked",
    tokenRequired: false,
    installSeed: "env_locked",
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_ADMIN,
        capabilities: {
          ...SERVER_CAPABILITIES,
          admin: true,
          personal_signing_keys: false,
        },
        csrf_token: ADMIN_CSRF,
      }),
  },
  {
    id: "install_fresh",
    tokenRequired: false,
    installSeed: "fresh",
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_ADMIN,
        capabilities: {
          ...SERVER_CAPABILITIES,
          admin: true,
          personal_signing_keys: false,
        },
        csrf_token: ADMIN_CSRF,
      }),
  },
  {
    id: "org_admin",
    tokenRequired: false,
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_ORG_ADMIN,
        capabilities: { ...SERVER_CAPABILITIES, admin: true },
        csrf_token: ORG_ADMIN_CSRF,
      }),
  },
  {
    id: "student_ready",
    tokenRequired: false,
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "domains",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_STUDENT,
        csrf_token: STUDENT_CSRF,
        inbox: { unread: 3 },
      }),
  },
  {
    id: "student_nosmtp",
    tokenRequired: false,
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "domains",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: false,
          password_min_length: 10,
        },
        user: DEMO_STUDENT,
        csrf_token: STUDENT_CSRF,
      }),
  },
  {
    id: "student_sso",
    tokenRequired: false,
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "closed",
          password_enabled: false,
          oidc_providers: [{ id: "keycloak", label: "HSE SSO" }],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_STUDENT,
        csrf_token: STUDENT_CSRF,
      }),
  },
  {
    id: "student_linked",
    tokenRequired: false,
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "domains",
          password_enabled: true,
          oidc_providers: [
            { id: "keycloak", label: "HSE SSO" },
            { id: "google", label: "Google" },
          ],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_STUDENT,
        csrf_token: STUDENT_CSRF,
      }),
  },
  {
    id: "newcomer",
    tokenRequired: false,
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_NEWCOMER,
        csrf_token: STUDENT_CSRF,
      }),
  },
  {
    id: "registration_closed",
    tokenRequired: false,
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "closed",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
      }),
  },
  {
    id: "sso_only",
    tokenRequired: false,
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "closed",
          password_enabled: false,
          oidc_providers: [
            { id: "keycloak", label: "HSE SSO" },
            { id: "google", label: "Google" },
          ],
          smtp_enabled: true,
          password_min_length: 10,
        },
      }),
  },
  {
    id: "registration_open",
    tokenRequired: false,
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "open",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
      }),
  },
  {
    id: "registration_domains",
    tokenRequired: false,
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "domains",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
      }),
  },
  {
    id: "registration_open_nosmtp",
    tokenRequired: false,
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "open",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: false,
          password_min_length: 10,
        },
      }),
  },
  // Личные раннеры: Анна с раннерами во всех состояниях, без раннеров, с
  // раннером не в сети и с выключенными администратором личными раннерами.
  {
    id: "runners_ready",
    tokenRequired: false,
    personalSeed: "default",
    bootstrap: () => personalBase(true),
  },
  {
    id: "runners_none",
    tokenRequired: false,
    personalSeed: "none",
    bootstrap: () => personalBase(true),
  },
  {
    id: "runners_offline",
    tokenRequired: false,
    personalSeed: "offline",
    bootstrap: () => personalBase(true),
  },
  {
    id: "runners_disabled",
    tokenRequired: false,
    personalSeed: "disabled",
    bootstrap: () => personalBase(false),
  },
  {
    id: "admin_personal_runners",
    tokenRequired: false,
    personalSeed: "default",
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_ADMIN,
        capabilities: {
          ...SERVER_CAPABILITIES,
          admin: true,
          personal_runners: true,
        },
        csrf_token: ADMIN_CSRF,
      }),
  },
  {
    id: "admin_runners_disabled",
    tokenRequired: false,
    personalSeed: "disabled",
    bootstrap: () =>
      base({
        auth: {
          registration_mode: "invite",
          password_enabled: true,
          oidc_providers: [],
          smtp_enabled: true,
          password_min_length: 10,
        },
        user: DEMO_ADMIN,
        capabilities: {
          ...SERVER_CAPABILITIES,
          admin: true,
          personal_runners: false,
        },
        csrf_token: ADMIN_CSRF,
      }),
  },
  // Локальная Студия с облачными сборками: только раздел «Облачные сборки»
  // ходит в демо-мир, остальное приложение работает как локальное.
  {
    id: "local_remote_off",
    tokenRequired: false,
    remoteSeed: "off",
    bootstrap: localBase,
  },
  {
    id: "local_remote_online",
    tokenRequired: false,
    remoteSeed: "online",
    bootstrap: localBase,
  },
  {
    id: "local_remote_problems",
    tokenRequired: false,
    remoteSeed: "docker_missing",
    bootstrap: localBase,
  },
  // links: гость по ссылке без входа (Борис с двумя открытыми ссылками).
  {
    id: "links_guest",
    tokenRequired: false,
    bootstrap: () => ({
      ...base({ csrf_token: GUEST_DEMO_CSRF, guest: GUEST_DEMO_INFO }),
      capabilities: {
        ...SERVER_CAPABILITIES,
        personal_signing_keys: false,
      },
    }),
  },
];

export const findServerScenario = (
  id: string,
): ServerDemoScenario | undefined =>
  SERVER_SCENARIOS.find((scenario) => scenario.id === id);
