import { matchPath } from "react-router";
import type { HelpMap } from "../api/helpApi";

/**
 * Статьи для текущего экрана, самая подходящая первой.
 *
 * Маршрут статьи — шаблон пути react-router (`/projects/:projectId/submit`), иногда с параметром
 * вкладки (`...?tab=checks`) или конкретным разделом (`/settings/providers`). Ранжирование:
 *  1. маршрут с совпавшим параметром запроса (вкладка — сама по себе экран);
 *  2. статья, у которой этот маршрут стоит ПЕРВЫМ (она про этот экран), а не упомянут дальше;
 *  3. порядок карты.
 * Маршрут с параметром запроса, который не совпал, не подходит вовсе.
 */
type Candidate = { key: string; order: number; rank: [number, number] };

const queryMatches = (expected: string, search: URLSearchParams): boolean =>
  [...new URLSearchParams(expected).entries()].every(
    ([name, value]) => search.get(name) === value,
  );

export const rankHelpKeys = (
  map: HelpMap,
  pathname: string,
  search: string,
): string[] => {
  const params = new URLSearchParams(search);
  const declared = new Map(map.articles.map((a) => [a.key, a.routes]));
  const best = new Map<string, Candidate>();
  let order = 0;
  for (const [route, keys] of Object.entries(map.routes)) {
    const [path = "", query] = route.split("?");
    if (!matchPath({ path, end: true }, pathname)) continue;
    if (query && !queryMatches(query, params)) continue;
    for (const key of keys) {
      const position = declared.get(key)?.indexOf(route) ?? -1;
      const rank: [number, number] = [
        query ? 0 : 1,
        position < 0 ? Number.MAX_SAFE_INTEGER : position,
      ];
      const previous = best.get(key);
      if (
        !previous ||
        rank[0] < previous.rank[0] ||
        (rank[0] === previous.rank[0] && rank[1] < previous.rank[1])
      ) {
        best.set(key, { key, order: previous?.order ?? order++, rank });
      }
    }
  }
  return [...best.values()]
    .sort(
      (a, b) =>
        a.rank[0] - b.rank[0] || a.rank[1] - b.rank[1] || a.order - b.order,
    )
    .map((c) => c.key);
};
