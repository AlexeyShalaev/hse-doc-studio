export type HostOs = "windows" | "macos" | "linux";

/**
 * Какую ОС считать хостовой.
 *
 * Спросить бэкенд нельзя: он живёт в Linux-контейнере и про машину пользователя
 * знает ровно ничего. Зато браузер, в котором открыт интерфейс, работает как раз
 * НА ХОСТЕ — его user agent и есть единственный доступный нам источник правды.
 */
export const detectHostOs = (): HostOs => {
  const platform = `${navigator.userAgent} ${navigator.platform}`.toLowerCase();
  if (platform.includes("win")) return "windows";
  if (platform.includes("mac")) return "macos";
  return "linux";
};

/**
 * Откуда начинать обзор.
 *
 * Домашний каталог КОНКРЕТНОГО пользователя нам неизвестен — из контейнера его
 * не видно, а браузер имени не выдаёт. Зато каталог, где живут все домашние
 * папки, у каждой ОС ровно один, и первый же его листинг показывает человеку
 * его собственное имя — дальше он идёт мышкой.
 */
export const homesRoot = (os: HostOs): string => {
  if (os === "windows") return "C:/Users";
  if (os === "macos") return "/Users";
  return "/home";
};

/**
 * Имя папки, которую мастер предлагает завести под работы.
 *
 * Совпадает с именем продукта и контейнера намеренно: увидев её на диске через
 * полгода, человек должен понять, чьё это, не открывая.
 */
export const DEFAULT_FOLDER_NAME = "hse-doc-studio";

const normalise = (path: string): string => path.replace(/\\/g, "/");

/** Разложить путь на сегменты вместе с абсолютным путём каждого — для «хлебных крошек». */
export type PathCrumb = {
  label: string;
  path: string;
};

export const toCrumbs = (path: string): PathCrumb[] => {
  const normalised = normalise(path).replace(/\/+$/, "");
  if (!normalised) return [];

  const windowsDrive = /^([A-Za-z]:)(.*)$/.exec(normalised);
  const drive = windowsDrive?.[1];
  const root = drive === undefined ? "/" : `${drive}/`;
  const rest = (drive === undefined ? normalised : windowsDrive?.[2]) ?? "";

  const crumbs: PathCrumb[] = [{ label: root, path: root }];
  let current = root;
  for (const segment of rest.split("/").filter(Boolean)) {
    current = joinPath(current, segment);
    crumbs.push({ label: segment, path: current });
  }
  return crumbs;
};

/** Приклеить сегмент, не удвоив разделитель у корня (`C:/`, `/`). */
export const joinPath = (base: string, segment: string): string => {
  const normalised = normalise(base);
  return normalised.endsWith("/")
    ? `${normalised}${segment}`
    : `${normalised}/${segment}`;
};

/** Родитель пути; null — выше уже некуда. */
export const parentPath = (path: string): string | null => {
  const crumbs = toCrumbs(path);
  if (crumbs.length < 2) return null;
  const parent = crumbs[crumbs.length - 2];
  return parent ? parent.path : null;
};

/** Последний сегмент — им подписывают выбранную папку. */
export const baseName = (path: string): string => {
  const crumbs = toCrumbs(path);
  const last = crumbs[crumbs.length - 1];
  return last ? last.label : path;
};

/**
 * Полный ли это путь. Относительный докер примет за ИМЯ ТОМА и смонтирует
 * пустоту вместо папки пользователя — проверяем до того, как звать сервер.
 */
export const isAbsoluteHostPath = (path: string): boolean => {
  const normalised = normalise(path).trim();
  return normalised.startsWith("/") || /^[A-Za-z]:\//.test(normalised);
};
