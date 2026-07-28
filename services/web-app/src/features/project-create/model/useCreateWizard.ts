import { create } from "zustand";

export type AuthorEntry = {
  name: string;
  group: string;
  // Team mode: each author defends their own part of the system.
  topic: string;
  // Team mode: folder slug the author's personal docs live under ("ivanov").
  slug: string;
  // false → the author's folder is not scaffolded; they keep files elsewhere.
  managed: boolean;
};

export type PersonRole = "university" | "company";
export type SupervisorEntry = {
  name: string;
  title: string;
  role: PersonRole;
  // Учёная степень — filled by the «Сотрудник из Вышки» picker; optional otherwise.
  degree: string;
};

// GOST-like RU→EN transliteration used to suggest the author's folder slug
// from the surname. The backend has its own translit fallback, but the wizard
// always sends the slug so a manual edit survives.
const TRANSLIT: Record<string, string> = {
  а: "a",
  б: "b",
  в: "v",
  г: "g",
  д: "d",
  е: "e",
  ё: "e",
  ж: "zh",
  з: "z",
  и: "i",
  й: "y",
  к: "k",
  л: "l",
  м: "m",
  н: "n",
  о: "o",
  п: "p",
  р: "r",
  с: "s",
  т: "t",
  у: "u",
  ф: "f",
  х: "h",
  ц: "ts",
  ч: "ch",
  ш: "sh",
  щ: "sch",
  ъ: "",
  ы: "y",
  ь: "",
  э: "e",
  ю: "yu",
  я: "ya",
};

// Author folder slugs must match the backend contract: ^[a-z][a-z0-9_]*$.
const SLUG_RE = /^[a-z][a-z0-9_]*$/;

export const isValidSlug = (slug: string): boolean => SLUG_RE.test(slug);

// Suggest a folder slug from the author's full name: take the surname (the
// first word of the ФИО), transliterate it and squeeze the result into the
// ^[a-z][a-z0-9_]*$ shape (leading non-letters and stray symbols dropped).
export const translitSlug = (fullName: string): string => {
  const surname = fullName.trim().split(/\s+/)[0] ?? "";
  let out = "";
  for (const ch of surname.toLowerCase()) {
    out += TRANSLIT[ch] ?? ch;
  }
  return out
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^[^a-z]+/, "")
    .replace(/_+$/, "");
};

// Suggest a folder-name slug from a project title: transliterate the WHOLE
// title RU→EN, lowercase it, and collapse everything that isn't a latin
// letter/digit into single dashes ("Мой проект 1" → "moy-proekt-1"). Unlike
// translitSlug (surname → author folder, "_"-joined) this is for the on-disk
// project folder appended after a picked/suggested parent.
export const titleSlug = (title: string): string => {
  let out = "";
  for (const ch of title.trim().toLowerCase()) {
    out += TRANSLIT[ch] ?? ch;
  }
  return out.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
};

export const emptyAuthor = (): AuthorEntry => ({
  name: "",
  group: "",
  topic: "",
  slug: "",
  managed: true,
});

type CreateWizardState = {
  step: number;
  // High-water mark of step indexes the user has reached via "Далее".
  // Sidebar navigation is gated by this so you can revisit prior steps but
  // cannot jump forward into ones you haven't validated through.
  maxReached: number;
  packId: string | null;
  templateId: string | null;
  version: string | null;
  kind: "research" | "project";
  title: string;
  folder: string;
  lang: "ru" | "en";
  // Chosen presentation-doc variant id (pptx / reveal / beamer …). null → the
  // backend picks the template's first variant. Set explicitly on the
  // «Формат презентации» step so the user doesn't miss the alternatives.
  presVariant: string | null;
  authors: AuthorEntry[];
  // Team mode: whether the shared/ docs group is scaffolded. Ignored for solo.
  sharedEnabled: boolean;
  supervisor: SupervisorEntry;
  coSupervisorEnabled: boolean;
  coSupervisor: SupervisorEntry;
  nda: boolean;
  meta: Record<string, unknown>;
  // actions
  nextStep: () => void;
  prevStep: () => void;
  goToStep: (i: number) => void;
  setField: <
    K extends keyof Omit<
      CreateWizardState,
      "nextStep" | "prevStep" | "goToStep" | "setField" | "reset"
    >,
  >(
    key: K,
    value: CreateWizardState[K],
  ) => void;
  reset: () => void;
};

const emptySupervisor = (): SupervisorEntry => ({
  name: "",
  title: "",
  role: "university",
  degree: "",
});

const initialState = {
  step: 0,
  maxReached: 0,
  packId: null,
  templateId: null,
  version: null,
  kind: "project" as "research" | "project",
  title: "",
  folder: "",
  lang: "ru" as const,
  presVariant: null as string | null,
  authors: [emptyAuthor()],
  sharedEnabled: true,
  supervisor: emptySupervisor(),
  coSupervisorEnabled: false,
  coSupervisor: emptySupervisor(),
  nda: false,
  meta: {},
};

export const useCreateWizard = create<CreateWizardState>((set) => ({
  ...initialState,

  nextStep: () => {
    set((s) => {
      const next = s.step + 1;
      return { step: next, maxReached: Math.max(s.maxReached, next) };
    });
  },
  prevStep: () => {
    set((s) => ({ step: Math.max(0, s.step - 1) }));
  },
  goToStep: (i: number) => {
    set((s) => ({ step: Math.min(Math.max(0, i), s.maxReached) }));
  },

  setField: (key, value) => {
    set({ [key]: value } as Partial<CreateWizardState>);
  },

  reset: () => {
    set({
      ...initialState,
      authors: [emptyAuthor()],
      supervisor: emptySupervisor(),
      coSupervisor: emptySupervisor(),
    });
  },
}));
