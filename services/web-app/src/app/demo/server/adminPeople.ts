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
  audit: Array.from({ length: 60 }, (_, i) => {
    const admin = i % 3 === 0;
    return {
      id: 60 - i,
      at: new Date(Date.now() - i * 3_600_000 * 5).toISOString(),
      action: admin ? "admin.user_approved" : "auth.login",
      actor_id: "u_01hx7k1a0b",
      target: admin ? "u_01hx7k2c1d" : null,
      details: admin ? {} : { method: "password" },
    };
  }),
});
