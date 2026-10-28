import type { Bootstrap, SessionUser } from "@entities/session";
import { seedProjects, type DemoProject } from "./projects";
import {
  ADMIN_CSRF,
  DEFAULT_DEMO_SETUP,
  DEFAULT_SERVER_SCENARIO_ID,
  DEMO_ADMIN,
  DEMO_STUDENT,
  STUDENT_CSRF,
  findServerScenario,
  type ServerDemoScenario,
  type ServerDemoSetup,
} from "./scenarios";

// Маркер для проверки сборки: в рабочий бандл этой строки попасть не должно.
export const SERVER_DEMO_WORLD_MARKER = "server-demo-world";

// Мир серверного демо: данные живут в памяти вкладки и сбрасываются со сменой сценария.
export type DemoSetupState = ServerDemoSetup & {
  settingsDone: boolean;
  completed: boolean;
  settings: {
    registration_mode: Bootstrap["auth"]["registration_mode"];
    registration_domains: string[];
    require_approval: boolean;
    password_enabled: boolean;
  };
};

export type ServerDemoWorld = {
  scenario: ServerDemoScenario;
  bootstrap: Bootstrap;
  /** Администратор создан мастером первого запуска. */
  adminCreated: boolean;
  /** Мастер первого запуска: что уже сделано и что показывает проверка окружения. */
  setup: DemoSetupState;
  /** Проекты мира: у каждого своя роль у каждого человека. */
  projects: DemoProject[];
};

const createSetupState = (scenario: ServerDemoScenario): DemoSetupState => {
  const setup = { ...DEFAULT_DEMO_SETUP, ...scenario.setup };
  const env = setup.locked.length > 0;
  return {
    ...setup,
    settingsDone: false,
    completed: false,
    // Окружение задало режим: в мастере он только читается, значения уже действуют.
    settings: {
      registration_mode: env
        ? "domains"
        : scenario.bootstrap().auth.registration_mode,
      registration_domains: env ? ["hse.ru", "edu.hse.ru"] : [],
      require_approval: env,
      password_enabled: true,
    },
  };
};

export const createServerWorld = (scenarioId: string): ServerDemoWorld => {
  const scenario =
    findServerScenario(scenarioId) ??
    findServerScenario(DEFAULT_SERVER_SCENARIO_ID);
  if (!scenario) throw new Error("server demo: no default scenario");
  return {
    scenario,
    bootstrap: scenario.bootstrap(),
    adminCreated: false,
    setup: createSetupState(scenario),
    projects: seedProjects(),
  };
};

/** Входит в мир: админ по своему адресу, остальные как студент. */
export const signIn = (world: ServerDemoWorld, email: string): SessionUser => {
  const isAdmin = email.trim().toLowerCase() === DEMO_ADMIN.email;
  const user = isAdmin ? DEMO_ADMIN : DEMO_STUDENT;
  world.bootstrap = {
    ...world.bootstrap,
    user,
    capabilities: { ...world.bootstrap.capabilities, admin: isAdmin },
    csrf_token: isAdmin ? ADMIN_CSRF : STUDENT_CSRF,
  };
  return user;
};

export const signOut = (world: ServerDemoWorld): void => {
  world.bootstrap = {
    ...world.bootstrap,
    user: null,
    capabilities: { ...world.bootstrap.capabilities, admin: false },
    csrf_token: null,
  };
};
