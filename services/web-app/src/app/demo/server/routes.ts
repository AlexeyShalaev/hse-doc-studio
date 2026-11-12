import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import { createSignerProfileDemo } from "@entities/signer-profile/testing";
import { createSigningIdentityDemo } from "@entities/signing-identity/testing";
import {
  DEMO_SIGNING_MEMBERS,
  DEMO_SIGNING_PROFILE,
  createSigningRouteDemo,
} from "@entities/signing-route/testing";
import { useServerDemoScenarioStore } from "./scenarioStore";
import { createAccountRoutes } from "./accountRoutes";
import { createAdminRoutes } from "./adminRoutes";
import { createAuthRoutes } from "./authRoutes";
import { catalogRoutes } from "./catalogRoutes";
import { createCheckpointDemo } from "./checkpointRoutes";
import { createSharedProviderUserRoutes } from "./installRoutes";
import { createInvitationRoutes } from "./invitationRoutes";
import { createMailLogAdminRoutes } from "./mailLog";
import { createMemberOrgRoutes } from "./memberOrgRoutes";
import { createGitRemoteRoutes } from "./gitRemoteRoutes";
import { createPersonalRoutes } from "./personalRoutes";
import { createProjectAccessRoutes } from "./projectAccessRoutes";
import { createProjectRoutes } from "./projectRoutes";
import { createReviewRoutes } from "./reviewRoutes";
import { createUsageRoutes } from "./quotaRoutes";
import { cloudDeviceDemoRoutes } from "../deviceRoutes";
import { createSetupRoutes } from "./setupRoutes";
import { createShareLinkRoutes, createSharingAdminRoutes } from "./shareLinks";
import { createSystemRoutes } from "./systemRoutes";
import {
  createStorageCleanupAccountRoutes,
  createStorageCleanupAdminRoutes,
} from "./storageCleanup";
import { DEMO_ADMIN, DEMO_STUDENT } from "./scenarios";
import { createServerWorld, signIn, signOut } from "./world";

// Серверное демо включается явно (VITE_SERVER_DEMO=1 или галерея /dev/server-screens).
// Пока оно выключено, обработчики отдают запрос дальше: демо git работает как раньше.
let active = false;
export const setServerDemoActive = (value: boolean): void => {
  active = value;
};
export const isServerDemoActive = (): boolean => active;

let world = createServerWorld(useServerDemoScenarioStore.getState().scenarioId);
export const getServerWorld = () => world;
// Маршрут подписания (docs/design/signing-route.md): бэкенда ещё нет, демо отвечает по
// контракту раздела 8 моками сущности. Проект виден, если он есть в мире демо.
// Подписант подписывает прямо на странице: ключи Студии (по политике установки) и
// сохранённая в профиле картинка тоже живут в памяти демо.
const serverKeysAllowed = (): boolean =>
  world.bootstrap.capabilities.personal_signing_keys;
export const signingIdentityDemo = createSigningIdentityDemo({
  getUser: () => world.bootstrap.user,
  allowed: serverKeysAllowed,
});
export const signerProfileDemo = createSignerProfileDemo({
  getUser: () => world.bootstrap.user,
});
// Точка сдачи с подписями и местами слотов: без неё не открыть карточку «Подписание».
export const checkpointDemo = createCheckpointDemo(
  () => world,
  () => signingRouteDemo,
);
export const signingRouteDemo = createSigningRouteDemo({
  getUser: () => world.bootstrap.user,
  projectName: (id) =>
    world.projects.find((p) => p.summary.id === id)?.summary.name ?? null,
  serverKeysAllowed,
  // Второй научрук: в редакторе маршрута видно, как выбирают одного из нескольких людей персоны.
  members: [
    ...DEMO_SIGNING_MEMBERS,
    {
      user_id: "u_demo_sidorova",
      name: "Сидорова А. В.",
      persona: "supervisor",
      plate: null,
    },
    // Академрук: его подпись автор добавляет к заявлению сам (сверх точки).
    {
      user_id: "u_demo_sidorov",
      name: "Сидоров С. С.",
      persona: "academic_supervisor",
      plate: null,
    },
  ],
  isPlaced: checkpointDemo.isPlaced,
  isOptional: checkpointDemo.isOptional,
  mailEnabled: () => world.bootstrap.auth.smtp_enabled,
  keysOf: (user) =>
    signingIdentityDemo.keysOf(user.id).map((key) => ({
      id: key.id,
      label: key.label,
      kind: key.kind,
      protected: key.protected,
      signer: key.subject_cn,
    })),
  onRememberImage: (user, image) => {
    signerProfileDemo.saveImage(user.id, image);
  },
});
const DAY_MS = 24 * 60 * 60 * 1000;
/**
 * Студента демо просят подписать в двух чужих проектах: так во «Входящих» есть раздел
 * «На подпись» (одна задача со сроком, одна просроченная) и работает страница подписанта.
 * В первом проекте автор уже разместил подпись научрука: подписанту доступны и картинка, и ЭП.
 * Во втором места нет, поэтому остаётся только способ точки (открепленная ЭП).
 *
 * Сценарии версии на подписи (docs/design/signing-route.md, раздел 12):
 * - `student_signing_versions`: свой маршрут студента в «Bertie» уже у научрука, а заявление
 *   потом пересобрано (есть изменения после отправки, «Отправить новую версию»); в первом чужом
 *   проекте студент согласовал, и автор прислал новую версию; второй чужой маршрут перенесён
 *   с 0.20.0 молча;
 * - `student_signing_migration`: свой маршрут студента с 0.20.0, версию не восстановить: стоит
 *   с `sent_changed`.
 *
 * Необязательные подписи (раздел 13), `student_signing_optional`: свой маршрут студента с
 * академруком сверх точки, его подпись отмечена необязательной; научрук согласовал, очередь
 * академрука, автор может его пропустить.
 */
const seedSigningTasks = (scenarioId: string): void => {
  if (world.bootstrap.user?.id !== DEMO_STUDENT.id) return;
  const signer = { id: DEMO_STUDENT.id, name: DEMO_STUDENT.name };
  const versions = scenarioId === "student_signing_versions";
  checkpointDemo.place("p_01hxa2f8gh", "topic_application", "supervisor");
  signingRouteDemo.seed({
    projectId: "p_01hxa2f8gh",
    sender: { id: DEMO_ADMIN.id, name: DEMO_ADMIN.name },
    signer,
    persona: "supervisor",
    deadline: new Date(Date.now() + 2 * DAY_MS).toISOString(),
    message: versions
      ? "Исправил формулировку темы, согласуйте, пожалуйста, ещё раз."
      : "Прошу согласовать тему до пятницы.",
    state: versions ? "new_version" : "sent",
  });
  signingRouteDemo.seed({
    projectId: "p_01hxa3k2jm",
    sender: { id: "u_01hx7k5pavel", name: "Павел Орлов" },
    signer,
    persona: "supervisor",
    deadline: new Date(Date.now() - DAY_MS).toISOString(),
    state: versions ? "migrated" : "sent",
  });
  if (scenarioId === "student_signing_optional") {
    const own = "p_01hxa1c4de";
    const petrov = DEMO_SIGNING_MEMBERS[0];
    for (const slot of ["supervisor", "academic_supervisor"])
      checkpointDemo.place(own, "topic_application", slot);
    signingRouteDemo.seedOptional({
      projectId: own,
      sender: signer,
      signer: { id: petrov?.user_id ?? "", name: petrov?.name ?? "" },
      academic: { id: "u_demo_sidorov", name: "Сидоров С. С." },
    });
    checkpointDemo.setOptional(
      own,
      DEMO_SIGNING_PROFILE.id,
      "topic_application",
      "academic_supervisor",
      true,
    );
  }
  if (versions || scenarioId === "student_signing_migration") {
    // Свой маршрут: место подписи научрука уже стоит, иначе новую версию не отправить.
    checkpointDemo.place("p_01hxa1c4de", "topic_application", "supervisor");
    const petrov = DEMO_SIGNING_MEMBERS[0];
    signingRouteDemo.seed({
      projectId: "p_01hxa1c4de",
      sender: signer,
      signer: { id: petrov?.user_id ?? "", name: petrov?.name ?? "" },
      persona: "supervisor",
      deadline: new Date(Date.now() + 3 * DAY_MS).toISOString(),
      message: "Прошу подписать заявление до пятницы.",
      state: versions ? "diverged" : "migration_lost",
    });
  }
};
seedSigningTasks(useServerDemoScenarioStore.getState().scenarioId);
export const resetServerWorld = (scenarioId: string): void => {
  world = createServerWorld(scenarioId);
  signingRouteDemo.reset();
  checkpointDemo.reset();
  signingIdentityDemo.reset();
  signerProfileDemo.reset();
  seedSigningTasks(scenarioId);
};

const guarded =
  (handler: DemoRoute["handler"]): DemoRoute["handler"] =>
  (req) =>
    active
      ? handler(req)
      : req.forward().then((res) => ({
          status: res.status,
          data: res.data as unknown,
        }));

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";

// Особые адреса демо: каждый возвращает свой отказ входа, чтобы все состояния экрана
// можно было вызвать руками.
const DEMO_LOGIN_REFUSALS: Record<
  string,
  {
    status: number;
    code: string;
    detail: string;
    extra?: Record<string, unknown>;
  }
> = {
  "locked@example.org": {
    status: 429,
    code: "rate_limited",
    detail: "Too many attempts",
    extra: { retry_after: 20 },
  },
  "unverified@example.org": {
    status: 403,
    code: "email_not_verified",
    detail: "Email is not verified",
  },
  "pending@example.org": {
    status: 403,
    code: "pending_approval",
    detail: "Account is pending approval",
  },
  "disabled@example.org": {
    status: 403,
    code: "account_disabled",
    detail: "Account is disabled",
  },
  "sso@example.org": {
    status: 403,
    code: "sso_login_required",
    detail: "Single sign-on required",
  },
};

const routes: DemoRoute[] = [
  {
    method: "GET",
    pattern: "/session/bootstrap",
    handler: () => demoJson(world.bootstrap),
  },
  {
    method: "POST",
    pattern: "/auth/login",
    handler: (req) => {
      const { auth } = world.bootstrap;
      const body = (req.body ?? {}) as Record<string, unknown>;
      if (!auth.password_enabled) {
        return demoError(
          403,
          "sso_login_required",
          "This email can only sign in through single sign-on",
        );
      }
      const refusal = DEMO_LOGIN_REFUSALS[str(body.email).trim().toLowerCase()];
      if (refusal) {
        return demoError(
          refusal.status,
          refusal.code,
          refusal.detail,
          refusal.extra,
        );
      }
      if (str(body.password).length < auth.password_min_length) {
        return demoError(
          401,
          "invalid_credentials",
          "Invalid email or password",
        );
      }
      const user = signIn(world, str(body.email));
      return demoJson({ user, csrf_token: world.bootstrap.csrf_token });
    },
  },
  {
    method: "POST",
    pattern: "/auth/logout",
    handler: () => {
      signOut(world);
      return demoNoContent();
    },
  },
];

const withGuard = (route: DemoRoute): DemoRoute => ({
  ...route,
  handler: guarded(route.handler),
});

/** Маршруты клиента /api/admin: ставятся на adminClient отдельно от /api/v1. */
export const serverAdminDemoRoutes: DemoRoute[] = [
  // Диски раннеров раньше маршрутов раннеров: «disk-summary» не должен уйти в /runners/:id.
  ...createStorageCleanupAdminRoutes(() => world),
  ...createMailLogAdminRoutes(() => world),
  ...createAdminRoutes(() => world),
  ...createSharingAdminRoutes(() => world),
].map(withGuard);

/** Маршруты клиента systemClient (/api/v1/system/*): у него свой транспорт. */
export const serverSystemDemoRoutes: DemoRoute[] = createSystemRoutes(
  () => world,
).map(withGuard);

export const serverDemoRoutes: DemoRoute[] = [
  ...routes,
  ...createAuthRoutes(() => world),
  ...createAccountRoutes(() => world),
  ...createSetupRoutes(() => world),
  // links: раньше маршрутов проектов, чтобы гость видел свой проект по ссылке.
  ...createShareLinkRoutes(() => world),
  ...createProjectRoutes(() => world),
  ...createProjectAccessRoutes(() => world),
  // Ревью-комментарии и комментарии из превью PDF.
  ...createReviewRoutes(() => world),
  // invites: приглашения, запросы доступа, передача владения, «Входящие».
  ...createInvitationRoutes(() => world, signingRouteDemo.taskCount),
  ...signingRouteDemo.routes,
  ...checkpointDemo.routes,
  ...signingIdentityDemo.routes,
  ...signerProfileDemo.routes,
  ...createMemberOrgRoutes(() => world),
  ...createStorageCleanupAccountRoutes(() => world),
  ...createPersonalRoutes(() => world),
  ...createUsageRoutes(() => world),
  ...createGitRemoteRoutes(() => world),
  ...createSharedProviderUserRoutes(() => world),
  ...cloudDeviceDemoRoutes,
  ...catalogRoutes,
].map((route) => ({
  ...route,
  handler: guarded(route.handler),
}));
