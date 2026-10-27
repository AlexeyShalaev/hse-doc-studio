import { DAY, HOUR, MINUTE, fakeSha, isoAgo } from "./clock";
import type { GitCommitBrief } from "@entities/git-sync";

export const ME = {
  name: "Иван Смирнов",
  email: "ivan.smirnov@edu.hse.ru",
};

export const TEAMMATES = [
  { name: "Анна Петрова", email: "anna.petrova@edu.hse.ru" },
  { name: "Дмитрий Орлов", email: "d.orlov@edu.hse.ru" },
];

const make = (
  seed: string,
  message: string,
  author: { name: string; email: string },
  agoMs: number,
  kind: string,
): GitCommitBrief => {
  const id = fakeSha(seed);
  return {
    id,
    short_id: id.slice(0, 7),
    message,
    author: author.name,
    author_email: author.email,
    created_at: isoAgo(agoMs),
    kind,
  };
};

const INCOMING_MESSAGES: [string, number, string][] = [
  ["Переписала введение", 20 * MINUTE, "edit"],
  ["Добавлен рисунок с архитектурой", 3 * HOUR, "manual"],
  ["Обновлён список литературы", 5 * HOUR, "edit"],
  ["Сборка документа", DAY, "compile"],
  ["Правки по замечаниям руководителя", 2 * DAY, "manual"],
  ["Новая глава: тестирование", 3 * DAY, "edit"],
];

const OUTGOING_MESSAGES: [string, number, string][] = [
  ["Дописан раздел про слияние", 10 * MINUTE, "edit"],
  ["Сборка документа", 45 * MINUTE, "compile"],
  ["Обновлена титульная страница", 2 * HOUR, "manual"],
  ["Исправлены ссылки на рисунки", 4 * HOUR, "edit"],
  ["Таблица сравнения подходов", DAY, "manual"],
  ["Черновик заключения", 2 * DAY, "edit"],
];

// Новые чужие версии (самые свежие первыми), не больше пяти, как отдаёт сервер.
export const incomingCommits = (count: number): GitCommitBrief[] =>
  INCOMING_MESSAGES.slice(0, Math.min(count, 5)).map(
    ([message, ago, kind], index) =>
      make(
        `in-${String(index)}`,
        message,
        TEAMMATES[index % TEAMMATES.length] ?? ME,
        ago,
        kind,
      ),
  );

// Свои неотправленные версии.
export const outgoingCommits = (count: number): GitCommitBrief[] =>
  OUTGOING_MESSAGES.slice(0, Math.min(count, 5)).map(
    ([message, ago, kind], index) =>
      make(`out-${String(index)}`, message, ME, ago, kind),
  );
