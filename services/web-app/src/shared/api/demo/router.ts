import type {
  DemoHandler,
  DemoMethod,
  DemoRoute,
  DemoRequest,
  DemoResponse,
} from "./types";

type CompiledRoute = {
  method: DemoMethod;
  regex: RegExp;
  names: string[];
  handler: DemoHandler;
};

export type DemoRouter = {
  match: (
    method: string,
    path: string,
  ) => { handler: DemoHandler; params: Record<string, string> } | null;
};

const escapeRegex = (value: string): string =>
  value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// "/projects/:projectId/git" -> регулярное выражение с именованными сегментами.
const compile = (route: DemoRoute): CompiledRoute => {
  const names: string[] = [];
  const source = route.pattern
    .split("/")
    .map((segment) => {
      if (segment.startsWith(":")) {
        names.push(segment.slice(1));
        return "([^/]+)";
      }
      return escapeRegex(segment);
    })
    .join("/");
  return {
    method: route.method,
    regex: new RegExp(`^${source}/?$`),
    names,
    handler: route.handler,
  };
};

export const createDemoRouter = (routes: readonly DemoRoute[]): DemoRouter => {
  const compiled = routes.map(compile);
  return {
    match: (method, path) => {
      const upper = method.toUpperCase();
      for (const route of compiled) {
        if (route.method !== upper) continue;
        const found = route.regex.exec(path);
        if (!found) continue;
        const params: Record<string, string> = {};
        route.names.forEach((name, index) => {
          params[name] = decodeURIComponent(found[index + 1] ?? "");
        });
        return { handler: route.handler, params };
      }
      return null;
    },
  };
};

export const demoJson = (data: unknown, status = 200): DemoResponse => ({
  status,
  data,
});

export const demoNoContent = (): DemoResponse => ({ status: 204 });

// Тело ошибки как у настоящего бэкенда: {detail, code, ...extra}.
export const demoError = (
  status: number,
  code: string,
  detail: string,
  extra: Record<string, unknown> = {},
): DemoResponse => ({
  status,
  data: { detail, code, ...extra },
});

export const queryString = (req: DemoRequest, key: string): string | null => {
  const value = req.query[key];
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
};
