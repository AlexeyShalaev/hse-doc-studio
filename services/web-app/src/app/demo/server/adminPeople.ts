import type {
  AdminAuditEvent,
  AdminInvitation,
  AdminUser,
} from "@entities/session";

// Люди установки в демо: аккаунты, очередь одобрений, приглашения и журнал аудита.

export type DemoAdminPeople = {
  users: AdminUser[];
  invitations: AdminInvitation[];
  audit: AdminAuditEvent[];
};

const day = 86_400_000;
const ago = (days: number): string =>
  new Date(Date.now() - days * day).toISOString();
const ahead = (days: number): string =>
  new Date(Date.now() + days * day).toISOString();

// Записи журнала за последние дни: разные действия и люди, как в живой
// установке. Цели записаны так же, как их пишет сервер: идентификаторы, а
// понятные имена в details.
const ADMIN = "u_01hx7k1a0b";
const RECENT_AUDIT: (Omit<AdminAuditEvent, "id" | "at"> & {
  minutesAgo: number;
})[] = [
  {
    minutesAgo: 6,
    action: "invite.create",
    actor_id: ADMIN,
    target: "inv_01",
    details: { email: "new.student@example.org", ttl_days: 7 },
  },
  {
    minutesAgo: 24,
    action: "auth.login",
    actor_id: "u_01hx7k2c1d",
    target: null,
    details: { method: "password", ip: "10.12.4.31" },
  },
  {
    minutesAgo: 38,
    action: "auth.login_failed",
    actor_id: null,
    target: null,
    details: {
      email: "petr.orlov@example.org",
      reason: "bad_password",
      ip: "185.12.40.7",
    },
  },
  {
    minutesAgo: 52,
    action: "runner.pause",
    actor_id: ADMIN,
    target: "rn_01hxb4",
    details: { name: "runner-4" },
  },
  {
    minutesAgo: 95,
    action: "settings.quotas_update",
    actor_id: ADMIN,
    target: null,
    details: { user_concurrent: 2, org_concurrent: 6 },
  },
  {
    minutesAgo: 150,
    action: "runner.registration_token_create",
    actor_id: ADMIN,
    target: "rt_01hxc1",
    details: { label: "Сервер в аудитории 305" },
  },
  {
    minutesAgo: 200,
    action: "org.create",
    actor_id: ADMIN,
    target: "org_01hxp3",
    details: { name: "Пилот 2026", slug: "pilot-2026" },
  },
  {
    minutesAgo: 260,
    action: "admin.user_approved",
    actor_id: ADMIN,
    target: "u_01hx7k2c1d",
    details: {},
  },
  {
    minutesAgo: 330,
    action: "settings.smtp_test",
    actor_id: ADMIN,
    target: null,
    details: { to: "ivan.sidorov@example.org" },
  },
  {
    minutesAgo: 26 * 60,
    action: "project.transfer",
    actor_id: "u_01hx7k2c1d",
    target: "prj_01hxq8",
    details: { title: "Курсовая работа: анализ рынка", to: "Пётр Орлов" },
  },
  {
    minutesAgo: 28 * 60,
    action: "group.member_add",
    actor_id: ADMIN,
    target: "grp_01hxm2",
    details: { name: "БПИ-231", email: "petr.orlov@example.org" },
  },
  {
    minutesAgo: 30 * 60,
    action: "settings.signing_policy_update",
    actor_id: ADMIN,
    target: null,
    details: { server_keys: "allowed" },
  },
  {
    minutesAgo: 31 * 60,
    action: "auth.oidc_provision",
    actor_id: "u_01hx7k3e2f",
    target: "u_01hx7k3e2f",
    details: { provider: "HSE SSO" },
  },
  {
    minutesAgo: 33 * 60,
    action: "admin.user_disabled",
    actor_id: ADMIN,
    target: "u_01hx7k6k5l",
    details: { reason: "Выпускница, доступ больше не нужен" },
  },
  {
    minutesAgo: 40 * 60,
    action: "oidc.delete",
    actor_id: ADMIN,
    target: "oidc_01hxk1",
    details: { label: "GitLab ВШЭ" },
  },
  {
    minutesAgo: 46 * 60,
    action: "admin.admin_granted",
    actor_id: ADMIN,
    target: "u_01hx7k2c1d",
    details: {},
  },
];

// Ровный фон старых записей: входы, одобрения, приглашения и доступы к проектам.
const OLDER_AUDIT: Omit<AdminAuditEvent, "id" | "at">[] = [
  {
    action: "auth.login",
    actor_id: ADMIN,
    target: null,
    details: { method: "password" },
  },
  {
    action: "admin.user_approved",
    actor_id: ADMIN,
    target: "u_01hx7k2c1d",
    details: {},
  },
  {
    action: "auth.login",
    actor_id: "u_01hx7k2c1d",
    target: null,
    details: { method: "oidc", provider: "HSE SSO" },
  },
  {
    action: "project.member_set",
    actor_id: "u_01hx7k2c1d",
    target: "prj_01hxq8",
    details: { title: "Курсовая работа: анализ рынка", role: "member" },
  },
  {
    action: "invite.create",
    actor_id: ADMIN,
    target: "inv_00",
    details: { email: "student@example.org" },
  },
  {
    action: "auth.logout",
    actor_id: "u_01hx7k3e2f",
    target: null,
    details: {},
  },
];

const olderAudit = (i: number): Omit<AdminAuditEvent, "id" | "at"> =>
  OLDER_AUDIT[i % OLDER_AUDIT.length] ?? {
    action: "auth.login",
    actor_id: ADMIN,
    target: null,
    details: {},
  };

/**
 * fresh: свежая установка, журнал пуст. no_runners: раннеров ещё не
 * подключали, в журнале нет записей о раннерах и их токенах.
 */
export type ServerDemoPeopleSeed = "default" | "fresh" | "no_runners";

const aboutRunners = (e: { action: string }): boolean =>
  e.action.startsWith("runner.");

export const createDemoAdminPeople = (
  seed: ServerDemoPeopleSeed = "default",
): DemoAdminPeople => ({
  users: [
    {
      id: "u_01hx7k1a0b",
      name: "Иван Сидоров",
      email: "ivan.sidorov@example.org",
      status: "active",
      is_instance_admin: true,
      created_at: ago(120),
      last_login_at: ago(0),
      project_count: 4,
    },
    {
      id: "u_01hx7k2c1d",
      name: "Мария Келлер",
      email: "maria.keller@example.org",
      status: "active",
      is_instance_admin: false,
      created_at: ago(90),
      last_login_at: ago(2),
      project_count: 3,
    },
    {
      id: "u_01hx7k3e2f",
      name: "Пётр Орлов",
      email: "petr.orlov@example.org",
      status: "active",
      is_instance_admin: false,
      created_at: ago(60),
      last_login_at: null,
      project_count: 0,
    },
    {
      id: "u_01hx7k4g3h",
      name: "Анна Волкова",
      email: "anna.volkova@example.org",
      status: "pending_approval",
      is_instance_admin: false,
      created_at: ago(1),
      last_login_at: null,
      project_count: 0,
    },
    {
      id: "u_01hx7k5i4j",
      name: "Олег Миронов",
      email: "oleg.mironov@example.org",
      status: "pending_verification",
      is_instance_admin: false,
      created_at: ago(2),
      last_login_at: null,
      project_count: 0,
    },
    {
      id: "u_01hx7k6k5l",
      name: "Дарья Лис",
      email: "darya.lis@example.org",
      status: "disabled",
      is_instance_admin: false,
      created_at: ago(200),
      last_login_at: ago(40),
      project_count: 0,
    },
    // Живая установка: преподаватели и студенты с разной давностью входа,
    // ещё две заявки в очереди одобрений.
    {
      id: "u_01hx7k7m6n",
      name: "Екатерина Смирнова",
      email: "e.smirnova@example.org",
      status: "active",
      is_instance_admin: false,
      created_at: ago(110),
      last_login_at: ago(0.08),
      project_count: 6,
    },
    {
      id: "u_01hx7k8p7q",
      name: "Алексей Новиков",
      email: "alexey.novikov@example.org",
      status: "active",
      is_instance_admin: false,
      created_at: ago(75),
      last_login_at: ago(5),
      project_count: 2,
    },
    {
      id: "u_01hx7k9r8s",
      name: "Софья Морозова",
      email: "sofya.morozova@example.org",
      status: "active",
      is_instance_admin: false,
      created_at: ago(64),
      last_login_at: ago(1),
      project_count: 5,
    },
    {
      id: "u_01hx7kat9u",
      name: "Никита Фёдоров",
      email: "nikita.fedorov@example.org",
      status: "active",
      is_instance_admin: false,
      created_at: ago(48),
      last_login_at: ago(14),
      project_count: 1,
    },
    {
      id: "u_01hx7kdw2x",
      name: "Полина Егорова",
      email: "polina.egorova@example.org",
      status: "active",
      is_instance_admin: false,
      created_at: ago(33),
      last_login_at: ago(31),
      project_count: 0,
    },
    {
      id: "u_01hx7kbu0v",
      name: "Ксения Лебедева",
      email: "ksenia.lebedeva@example.org",
      status: "pending_approval",
      is_instance_admin: false,
      created_at: ago(0.2),
      last_login_at: null,
      project_count: 0,
    },
    {
      id: "u_01hx7kcv1w",
      name: "Артём Ковалёв",
      email: "artem.kovalev@example.org",
      status: "pending_approval",
      is_instance_admin: false,
      created_at: ago(3),
      last_login_at: null,
      project_count: 0,
    },
  ],
  invitations: [
    {
      id: "inv_01",
      email: "new.student@example.org",
      status: "pending",
      expires_at: ahead(5),
      used_at: null,
    },
    {
      id: "inv_02",
      email: null,
      status: "pending",
      expires_at: ahead(2),
      used_at: null,
    },
    {
      id: "inv_03",
      email: "maria.keller@example.org",
      status: "used",
      expires_at: ago(80),
      used_at: ago(90),
    },
    {
      id: "inv_04",
      email: "old@example.org",
      status: "expired",
      expires_at: ago(10),
      used_at: null,
    },
  ],
  audit:
    seed === "fresh"
      ? []
      : [
          ...RECENT_AUDIT.filter(
            (e) => seed !== "no_runners" || !aboutRunners(e),
          ).map(({ minutesAgo, ...e }, i) => ({
            ...e,
            id: 60 + RECENT_AUDIT.length - i,
            at: new Date(Date.now() - minutesAgo * 60_000).toISOString(),
          })),
          ...Array.from({ length: 60 }, (_, i) => ({
            ...olderAudit(i),
            id: 60 - i,
            at: new Date(Date.now() - (i * 5 + 50) * 3_600_000).toISOString(),
          })),
        ],
});
