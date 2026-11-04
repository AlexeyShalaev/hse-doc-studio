import type { StudioLink } from "../model/device.schema";
import type {
  PersonOnline,
  ProjectPeople,
  ReportedActivity,
} from "../model/people.schema";

/** Сколько аватаров показывать в шапке: остальные сворачиваются в «+N». */
export const MAX_AVATARS = 5;
/** Не чаще одного сигнала за это время, как бы часто ни менялось место. */
export const MIN_SIGNAL_GAP_MS = 5_000;
/** Смена места ждёт это время: быстрое перелистывание вкладок даёт один сигнал. */
export const PLACE_DEBOUNCE_MS = 1_500;
export const DEFAULT_INTERVAL_S = 60;

const SESSION_KEY = "hds.presence.session";

const randomId = (): string => {
  const bytes = new Uint8Array(12);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
};

/**
 * Идентификатор вкладки. Живёт в sessionStorage: перезагрузка вкладки сохраняет его (в списке не появляется
 * лишний «призрак»), новая вкладка получает свой. Хранилища нет (приватный режим): идентификатор на время страницы.
 */
let memoryId: string | null = null;
export const tabSessionId = (): string => {
  try {
    const stored = window.sessionStorage.getItem(SESSION_KEY);
    if (stored !== null && /^[A-Za-z0-9_-]{8,64}$/.test(stored)) return stored;
    const fresh = randomId();
    window.sessionStorage.setItem(SESSION_KEY, fresh);
    return fresh;
  } catch {
    memoryId ??= randomId();
    return memoryId;
  }
};

export type VisiblePeople = {
  shown: PersonOnline[];
  hidden: number;
};

/** Первые `limit` человек, остальные счётчиком; свой аватар всегда в числе показанных. */
export const splitPeople = (
  people: readonly PersonOnline[],
  total: number,
  limit: number = MAX_AVATARS,
): VisiblePeople => {
  const shown = people.slice(0, limit);
  const mine = people.find((p) => p.me);
  if (mine !== undefined && !shown.includes(mine) && shown.length > 0) {
    shown[shown.length - 1] = mine;
  }
  return { shown, hidden: Math.max(0, total - shown.length) };
};

/** Работает ли человек именно с веба, со Студии или с обоих мест (подпись «с какого устройства»). */
export type DeviceKind = "web" | "studio" | "both";
export const deviceKind = (
  person: Pick<PersonOnline, "channels">,
): DeviceKind => {
  const web = person.channels.includes("web");
  const studio = person.channels.includes("studio");
  return web && studio ? "both" : studio ? "studio" : "web";
};

/** Видимое место человека: документ, к которому можно перейти, или null. */
export const hasDocument = (person: PersonOnline): boolean =>
  person.doc_id !== null && person.activity !== "local";

/** Режимы документа, которые вкладка умеет сообщить. */
export type DocActivity = Extract<
  ReportedActivity,
  "editing" | "viewing" | "reviewing" | "building"
>;

/** Локальная Студия: люди из ответа облака на рабочем сервере; null, если сервер не вошёл или список не отдал. */
export const pickPeople = (
  link: StudioLink | undefined,
): ProjectPeople | null => {
  if (link === undefined) return null;
  const server = link.servers.find((s) => s.state === "ok");
  return server?.cloud?.people ?? null;
};
