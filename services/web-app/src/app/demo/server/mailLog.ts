import type { DemoRoute } from "@shared/api/demo";
import {
  createMailLogDemo,
  type MailJournalProfile,
  type MailLogDemo,
  type MailLogRecord,
} from "@features/admin-mail-log/testing";
import { delegate } from "./storageCleanup";
import { adminSettingsOf, type ServerDemoWorld } from "./world";

// Журнал писем в админке (docs/design/mail-log.md, раздел 6). Бэкенда ещё нет (B1..B6): мир
// отвечает моками фичи. Журнал строится при первом обращении и сбрасывается со сменой сценария.
//
// Какой журнал у какого сценария:
//  - admin_scale: большой журнал за срок хранения, листание по курсору;
//  - admin_sso: почта не настроена, за сутки письма «не отправлялось», раньше уходили;
//  - ops_services_degraded: SMTP-сервер отклоняет вход, за три часа все письма «не ушло» (auth);
//  - ops_fresh, install_fresh и мастер первого запуска: писем ещё не было;
//  - остальные: обычный день, все виды и итоги.
// Настроена ли почта, говорит блок «Почта (SMTP)» мира: выключили там, и плашка появится.
// Тестовое письмо из этого блока дописывает строку в журнал (adminRoutes, /settings/smtp/test).

const profileOf = (world: ServerDemoWorld): MailJournalProfile => {
  const { scenario } = world;
  if (scenario.scale) return "busy";
  if (scenario.adminSeed === "sso") return "smtp_off";
  if (scenario.opsSeed === "services_degraded") return "auth_failure";
  if (
    scenario.opsSeed === "fresh" ||
    scenario.installSeed === "fresh" ||
    world.bootstrap.setup_state !== "ready"
  ) {
    return "empty";
  }
  return "default";
};

/** Журнал писем мира; строится при первом обращении. */
export const mailLogOf = (world: ServerDemoWorld): MailLogDemo => {
  world.mailLog ??= createMailLogDemo({
    getActor: () => {
      const user = world.bootstrap.user;
      return user
        ? { id: user.id, name: user.name, admin: user.is_instance_admin }
        : null;
    },
    profile: () => profileOf(world),
    smtpConfigured: () => adminSettingsOf(world).smtp.enabled,
  });
  return world.mailLog;
};

/**
 * Тестовое письмо в журнале: без SMTP сервер отвечает 422 и строки не пишет (5.3, P15), иначе
 * строка «Отправлено» или «Не ушло» от имени вошедшего админа.
 */
export const recordSmtpTest = (
  world: ServerDemoWorld,
  to: string,
  failure: string | null,
): MailLogRecord | null => {
  const user = world.bootstrap.user;
  if (!user || !adminSettingsOf(world).smtp.enabled) return null;
  const actor = { id: user.id, name: user.name, email: user.email };
  const person = to.toLowerCase() === user.email.toLowerCase() ? actor : null;
  return mailLogOf(world).record({
    template: "smtp_test",
    lang: user.locale === "en" ? "en" : "ru",
    to: person ?? to,
    subject:
      user.locale === "en"
        ? "HSE Doc Studio: mail check"
        : "HSE Doc Studio: проверка почты",
    status: failure === null ? "sent" : "failed",
    ...(failure === null
      ? {}
      : { reason: "connect", error: failure, duration_ms: 3010 }),
    cause: "user",
    actor,
    origin: "smtp_test",
    values: { server: "studio.example.org" },
  });
};

const TEMPLATE = createMailLogDemo({
  getActor: () => null,
  profile: () => "empty",
  smtpConfigured: () => false,
});

/** Маршруты клиента /api/admin: журнал, сводка за сутки и карточка письма. */
export const createMailLogAdminRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => delegate(TEMPLATE.routes, () => mailLogOf(getWorld()).routes);
