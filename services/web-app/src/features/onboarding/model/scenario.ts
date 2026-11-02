import type { OnboardingAnswers } from "@entities/onboarding";

/**
 * Версия сценария. Поднимается, когда тур меняется настолько, что прошедшим его
 * стоит предложить посмотреть заново (приглашение, не автозапуск).
 */
export const SCENARIO_VERSION = 1;

export type Role = "student" | "supervisor" | "admin";
export type Skill = "none" | "some" | "pro";

/** Событие песочницы, после которого шаг считается выполненным. */
export type DemoEvent =
  | "project-created"
  | "edited"
  | "built"
  | "agent-done"
  | "review-resolved"
  | "git-pushed";

/** Действие песочницы, которое главная кнопка шага выполняет «за человека». */
export type DemoAction =
  "create" | "edit" | "build" | "ask-agent" | "resolve-comment" | "git-sync";

export type TourPhase = "interface" | "demo";

export type TourStep = {
  /** Стабильный id: на него ссылаются документация и сохранённый прогресс. */
  id: string;
  phase: TourPhase;
  /** Значение атрибута data-tour у подсвечиваемого элемента. */
  target?: string;
  /** Ключ текста в словаре onboarding (`steps.<textKey>.title|body`). */
  textKey: string;
  waitFor?: DemoEvent;
  action?: DemoAction;
  /** Подсказка разрешает клики по подсвеченному элементу. */
  interactive?: boolean;
};

export type ScenarioContext = {
  mode: "local" | "server";
  isAdmin: boolean;
};

export const roleOf = (answers: OnboardingAnswers): Role | null =>
  answers.role === "student" ||
  answers.role === "supervisor" ||
  answers.role === "admin"
    ? answers.role
    : null;

const skillOf = (value: string | undefined): Skill | null =>
  value === "none" || value === "some" || value === "pro" ? value : null;

export const INTERFACE_STEPS: readonly TourStep[] = [
  {
    id: "home.new-project",
    phase: "interface",
    target: "home-new-project",
    textKey: "homeNewProject",
  },
  {
    id: "home.search",
    phase: "interface",
    target: "home-search",
    textKey: "homeSearch",
  },
  {
    id: "home.agent",
    phase: "interface",
    target: "titlebar-agent",
    textKey: "homeAgent",
  },
  {
    id: "home.settings",
    phase: "interface",
    target: "titlebar-settings",
    textKey: "homeSettings",
  },
  {
    id: "home.admin",
    phase: "interface",
    target: "titlebar-account",
    textKey: "homeAdmin",
  },
  {
    id: "home.help",
    phase: "interface",
    target: "titlebar-help",
    textKey: "homeHelp",
  },
];

export const DEMO_STEPS: readonly TourStep[] = [
  { id: "demo.intro", phase: "demo", textKey: "demoIntro" },
  {
    id: "demo.create",
    phase: "demo",
    target: "demo-create",
    textKey: "demoCreate",
    waitFor: "project-created",
    action: "create",
    interactive: true,
  },
  {
    id: "demo.files",
    phase: "demo",
    target: "demo-files",
    textKey: "demoFiles",
    interactive: true,
  },
  {
    id: "demo.latex",
    phase: "demo",
    target: "demo-editor",
    textKey: "demoLatex",
  },
  {
    id: "demo.edit",
    phase: "demo",
    target: "demo-editor",
    textKey: "demoEdit",
    waitFor: "edited",
    action: "edit",
    interactive: true,
  },
  {
    id: "demo.build",
    phase: "demo",
    target: "demo-build",
    textKey: "demoBuild",
    waitFor: "built",
    action: "build",
    interactive: true,
  },
  {
    id: "demo.preview",
    phase: "demo",
    target: "demo-preview",
    textKey: "demoPreview",
  },
  {
    id: "demo.agent",
    phase: "demo",
    target: "demo-agent",
    textKey: "demoAgent",
    waitFor: "agent-done",
    action: "ask-agent",
    interactive: true,
  },
  {
    id: "demo.review",
    phase: "demo",
    target: "demo-review",
    textKey: "demoReview",
    waitFor: "review-resolved",
    action: "resolve-comment",
    interactive: true,
  },
  {
    id: "demo.git",
    phase: "demo",
    target: "demo-git",
    textKey: "demoGit",
    waitFor: "git-pushed",
    action: "git-sync",
    interactive: true,
  },
];

/**
 * Шаги тура по ответам анкеты:
 * - админу экскурсия показывает вход в админку (меню аккаунта, только сервер);
 * - тому, кто не знаком с LaTeX, демо объясняет разметку отдельным шагом;
 * - руководителю и тому, кто знает git, тексты шагов замечаний и git свои (вариант текста).
 */
export const buildSteps = (
  answers: OnboardingAnswers,
  ctx: ScenarioContext,
  phases: readonly TourPhase[] = ["interface", "demo"],
): TourStep[] => {
  const role = roleOf(answers);
  const latex = skillOf(answers.latex);
  const showAdmin =
    ctx.mode === "server" && ctx.isAdmin && (role === "admin" || role === null);
  return [...INTERFACE_STEPS, ...DEMO_STEPS].filter((step) => {
    if (!phases.includes(step.phase)) return false;
    if (step.id === "home.admin") return showAdmin;
    if (step.id === "demo.latex") return latex !== "pro" && latex !== "some";
    return true;
  });
};

/** Вариант текста шага по ответам (`steps.<key>.body_<variant>`), если он есть. */
export const textVariant = (
  step: TourStep,
  answers: OnboardingAnswers,
): string | null => {
  if (step.id === "demo.review" && roleOf(answers) === "supervisor") {
    return "supervisor";
  }
  if (step.id === "demo.git") {
    const git = skillOf(answers.git);
    if (git === "none") return "beginner";
    if (git === "pro") return "pro";
  }
  if (step.id === "demo.agent" && roleOf(answers) === "supervisor") {
    return "supervisor";
  }
  return null;
};
