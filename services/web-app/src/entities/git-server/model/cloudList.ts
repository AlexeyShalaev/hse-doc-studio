import type { CloudProject, CloudServer } from "./gitServer.schema";

/** Облачный проект вместе с сервером, на котором он лежит. */
export type CloudEntry = { server: CloudServer; project: CloudProject };

export type CloudListView = {
  /** Проекты, которых ещё нет на компьютере: в списке они идут карточками «Облако». */
  remote: CloudEntry[];
  /** Идентификатор локального проекта → сервер, на котором у человека есть такой же проект. */
  linked: Map<string, CloudServer>;
  /** Серверы, где список не получен: доступ истёк, отозван или нет связи. */
  problems: CloudServer[];
  /** Серверы, где проектов больше, чем показано. */
  truncated: CloudServer[];
  /** Серверы, где у человека пока нет проектов. */
  empty: CloudServer[];
};

/**
 * Сопоставление облачных проектов с локальными по идентификатору проекта на сервере: открытый
 * на компьютере проект не дублируется карточкой «Облако», а получает на своей карточке пометку.
 * Один проект на двух серверах показывается один раз, по первому серверу.
 */
export const buildCloudList = (
  servers: readonly CloudServer[],
  localIds: ReadonlySet<string>,
): CloudListView => {
  const view: CloudListView = {
    remote: [],
    linked: new Map(),
    problems: [],
    truncated: [],
    empty: [],
  };
  const seen = new Set<string>();
  for (const server of servers) {
    if (server.state !== "ok") {
      view.problems.push(server);
      continue;
    }
    if (server.total === 0) view.empty.push(server);
    else if (server.total > server.projects.length) view.truncated.push(server);
    for (const project of server.projects) {
      const id = project.id.toLowerCase();
      const here = project.is_local || localIds.has(id);
      if (here) {
        if (!view.linked.has(id)) view.linked.set(id, server);
      } else if (!seen.has(id)) {
        seen.add(id);
        view.remote.push({ server, project });
      }
    }
  }
  return view;
};
