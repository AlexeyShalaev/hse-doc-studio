import { useEffect, useRef } from "react";
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import { ZodError, type ZodIssue } from "zod";
import { ApiError } from "@shared/api/client";
import { SchemaParseError } from "@shared/api/parse";
import {
  useApplyTheme,
  useApplyLanguage,
  useThemeStore,
  i18n,
  toast,
} from "@shared/lib";

type AnyQuery = { queryKey: readonly unknown[] };

const MAX_BODY_CHARS = 4000;

const getAtPath = (data: unknown, path: readonly PropertyKey[]): unknown => {
  let cur: unknown = data;
  for (const seg of path) {
    if (cur == null) return undefined;
    if (typeof seg === "string" && typeof cur === "object") {
      cur = (cur as Record<string, unknown>)[seg];
    } else if (typeof seg === "number" && Array.isArray(cur)) {
      cur = cur[seg];
    } else {
      return undefined;
    }
  }
  return cur;
};

const safeStringify = (value: unknown, max = 300): string => {
  if (value === undefined) return "undefined";
  try {
    const s = JSON.stringify(value, null, 2);
    // JSON.stringify() only yields undefined for functions, symbols and
    // objects whose toJSON() returns undefined (plain undefined is handled
    // above). Functions and symbols stringify meaningfully; anything left is
    // an object whose String() would just be a useless "[object Object]".
    if (s == null) {
      return typeof value === "function" || typeof value === "symbol"
        ? String(value)
        : "<unserializable>";
    }
    return s.length <= max
      ? s
      : `${s.slice(0, max)}…[truncated, ${s.length.toString()} chars]`;
  } catch {
    return "<unserializable>";
  }
};

const issueLine = (issue: ZodIssue, data: unknown): string => {
  const path = issue.path.length === 0 ? "(root)" : issue.path.join(".");
  const received = issue.path.length === 0 ? data : getAtPath(data, issue.path);
  const issueDump = safeStringify(issue, 600).replace(/\n/g, "\n      ");
  return `  • path: ${path}
    code:     ${issue.code}
    message:  ${issue.message}
    received: ${safeStringify(received, 300).replace(/\n/g, "\n              ")}
    full issue:
      ${issueDump}`;
};

const formatSchemaReport = (err: SchemaParseError): string => {
  const issues = err.zodError.issues
    .map((i) => issueLine(i, err.responseData))
    .join("\n");
  let body = "<no data>";
  try {
    body =
      JSON.stringify(err.responseData, null, 2) ?? String(err.responseData);
    if (body.length > MAX_BODY_CHARS) {
      body = `${body.slice(0, MAX_BODY_CHARS)}\n…[truncated, ${body.length.toString()} chars total]`;
    }
  } catch {
    body = "<unserializable>";
  }
  return `── Несовпадение Zod-схемы ───────────────────────────────
request:  ${err.requestMethod} ${err.requestUrl}
issues:   ${err.zodError.issues.length.toString()}

Issues (path → code → received):
${issues}

Полное тело ответа (для отладки / отправки агенту):
${body}
──────────────────────────────────────────────────────────`;
};

const queryScope = (q: AnyQuery | undefined): string =>
  q
    ? `query [${q.queryKey.map((k) => JSON.stringify(k)).join(", ")}]`
    : "query";

const reportError = (error: unknown, source: string): void => {
  if (error instanceof ApiError) return; // already toasted by axios interceptor

  if (error instanceof SchemaParseError) {
    const report = formatSchemaReport(error);
    /* eslint-disable no-console */
    console.groupCollapsed(
      `%c[Schema] ${error.requestMethod} ${error.requestUrl}`,
      "color: #ff7a8a; font-weight: 600",
    );
    console.error(report);
    console.error("ZodError.issues:", error.zodError.issues);
    console.error("response.data:", error.responseData);
    console.groupEnd();
    /* eslint-enable no-console */
    toast.error(
      i18n.t("errors:message.schemaConsole", {
        method: error.requestMethod,
        url: error.requestUrl,
      }),
      i18n.t("errors:title.schemaMismatch"),
    );
    return;
  }

  if (error instanceof ZodError) {
    /* eslint-disable no-console */
    console.groupCollapsed(
      `%c[Zod] ${source}`,
      "color: #ff7a8a; font-weight: 600",
    );
    console.error("issues:", error.issues);
    console.groupEnd();
    /* eslint-enable no-console */
    toast.error(
      i18n.t("errors:message.zodNoHttp"),
      i18n.t("errors:title.schemaMismatch"),
    );
    return;
  }

  if (error instanceof Error) {
    console.error(`[Error] ${source}:`, error);
    toast.error(
      error.message || i18n.t("errors:message.unknown"),
      i18n.t("errors:title.generic"),
    );
    return;
  }

  console.error(`[Unknown] ${source}:`, error);
  toast.error(String(error), i18n.t("errors:title.generic"));
};

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
  queryCache: new QueryCache({
    onError: (error, query) => {
      reportError(error, queryScope(query));
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _vars, _ctx, mutation) => {
      const keyPart = mutation.options.mutationKey
        ? mutation.options.mutationKey.map((k) => JSON.stringify(k)).join(", ")
        : "(no mutationKey)";
      reportError(error, `mutation [${keyPart}]`);
    },
  }),
});

type ProvidersProps = {
  children: React.ReactNode;
};

const ThemeBridge = ({ children }: ProvidersProps) => {
  useApplyTheme();
  return <>{children}</>;
};

// Broadcasts the interface language (useThemeStore.lang) to i18next + html[lang],
// and refetches backend-localized data on a language change. Several backend
// responses now follow the interface language (agent personas, check
// diagnostics, error messages…) and are cached with language-agnostic query
// keys (some with staleTime: Infinity), so a runtime language switch must
// invalidate them to pull the new language. The axios interceptor already
// attaches the current language to every request.
const LanguageBridge = ({ children }: ProvidersProps) => {
  useApplyLanguage();
  const lang = useThemeStore((s) => s.lang);
  const isFirst = useRef(true);
  useEffect(() => {
    if (isFirst.current) {
      isFirst.current = false;
      return;
    }
    void queryClient.invalidateQueries();
  }, [lang]);
  return <>{children}</>;
};

export const Providers = ({ children }: ProvidersProps) => (
  <QueryClientProvider client={queryClient}>
    <I18nextProvider i18n={i18n}>
      <ThemeBridge>
        <LanguageBridge>{children}</LanguageBridge>
      </ThemeBridge>
    </I18nextProvider>
  </QueryClientProvider>
);
