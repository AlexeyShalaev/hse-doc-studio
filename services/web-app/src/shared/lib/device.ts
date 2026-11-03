// Краткое описание устройства по строке User-Agent: «Chrome · macOS».
// Полная строка остаётся в подсказке, если разобрать её не удалось, показываем её как есть.

const BROWSERS: readonly [RegExp, string][] = [
  [/\bEdg(?:e|A|iOS)?\//, "Edge"],
  [/\bOPR\/|\bOpera\b/, "Opera"],
  [/\bYaBrowser\//, "Яндекс Браузер"],
  [/\bFirefox\/|\bFxiOS\//, "Firefox"],
  [/Chrome\/|\bCriOS\//, "Chrome"],
  [/\bSafari\//, "Safari"],
  [/\bcurl\//i, "curl"],
];

const SYSTEMS: readonly [RegExp, string][] = [
  [/\bAndroid\b/, "Android"],
  [/\biPhone\b|\biPad\b|\biPod\b/, "iOS"],
  [/\bWindows\b/, "Windows"],
  [/\bMac OS X\b|\bMacintosh\b/, "macOS"],
  [/\bCrOS\b/, "ChromeOS"],
  [/\bLinux\b|\bX11\b/, "Linux"],
];

const firstMatch = (
  table: readonly [RegExp, string][],
  agent: string,
): string | null => table.find(([re]) => re.test(agent))?.[1] ?? null;

/** «Chrome · macOS», «Firefox», «macOS» или пустая строка, если ничего не распознано. */
export const describeAgent = (agent: string): string =>
  [firstMatch(BROWSERS, agent), firstMatch(SYSTEMS, agent)]
    .filter((part): part is string => part !== null)
    .join(" · ");
