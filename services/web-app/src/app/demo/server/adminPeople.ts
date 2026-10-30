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

// Свежие записи журнала: разные действия и люди, как в живой установке. Цели
// записаны так же, как их пишет сервер: идентификаторы, подробности в details.
const RECENT_AUDIT: (Omit<AdminAuditEvent, "id" | "at"> & {
  minutesAgo: number;
})[] = [
  {
    minutesAgo: 6,
    action: "invite.create",
    actor_id: "u_01hx7k1a0b",
    target: "inv_01",
    details: { email: "new.student@example.org" },
  },
  {
    minutesAgo: 24,
    action: "auth.login",
    actor_id: "u_01hx7k2c1d",
    target: null,
    details: { method: "password" },
  },
  {
    minutesAgo: 52,
    action: "runner.pause",
    actor_id: "u_01hx7k1a0b",
    target: "rn_01hxb4",
    details: {},
  },
  {
    minutesAgo: 95,
    action: "settings.quotas_update",
    actor_id: "u_01hx7k1a0b",
    target: null,
    details: { user_concurrent: 2, org_concurrent: 6 },
  },
  {
    minutesAgo: 150,
    action: "runner.registration_token_create",
    actor_id: "u_01hx7k1a0b",
    target: "rt_01hxc1",
    details: { label: "Сервер в аудитории 305" },
  },
  {
    minutesAgo: 200,
    action: "org.create",
    actor_id: "u_01hx7k1a0b",
    target: "org_01hxp3",
    details: { slug: "pilot-2026" },
  },
];

export const createDemoAdminPeople = (): DemoAdminPeople => ({
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
  audit: [
    ...RECENT_AUDIT.map(({ minutesAgo, ...e }, i) => ({
      ...e,
      id: 60 + RECENT_AUDIT.length - i,
      at: new Date(Date.now() - minutesAgo * 60_000).toISOString(),
    })),
    ...Array.from({ length: 60 }, (_, i) => {
      const admin = i % 3 === 0;
      return {
        id: 60 - i,
        at: new Date(Date.now() - (i * 5 + 4) * 3_600_000).toISOString(),
        action: admin ? "admin.user_approved" : "auth.login",
        actor_id: "u_01hx7k1a0b",
        target: admin ? "u_01hx7k2c1d" : null,
        details: admin ? {} : { method: "password" },
      };
    }),
  ],
});
