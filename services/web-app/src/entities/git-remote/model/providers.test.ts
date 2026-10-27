import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { GIT_PROVIDERS, type GitProvider } from "../api/gitRemoteSchemas";
import {
  PROVIDER_CATALOG,
  apiBase,
  assessScopes,
  detectProvider,
  instancePrefixCandidates,
  providerForHost,
  providerSpec,
  webBase,
} from "./providerCatalog";
import {
  cleanText,
  defaultTokenDescription,
  defaultTokenName,
  encodeComponent,
  sshLinks,
  tokenLinks,
} from "./providerLinks";

const CONTRACT = join(
  import.meta.dirname,
  "..",
  "..",
  "..",
  "..",
  "..",
  "..",
  "contracts",
  "git-sync",
);

type Link = { kind: "prefilled" | "plain"; url: string; broad: boolean } | null;
type Api = { provider: GitProvider; version: string | null };

type Vectors = {
  host_cases: {
    host: string | null;
    overrides?: Record<string, GitProvider>;
    api?: Api;
    expect: unknown;
  }[];
  web_base_cases: {
    host: string | null;
    port: number | null;
    secure: boolean;
    subpath: string;
    expect: string | null;
  }[];
  api_base_cases: {
    provider: GitProvider;
    host: string | null;
    web_base: string | null;
    expect: string | null;
  }[];
  prefix_cases: { segments: string[]; expect: string[] }[];
  text_cases: {
    kind: string;
    project?: string | null;
    date?: string;
    lang?: string;
    text?: string;
    limit?: number;
    expect: string;
  }[];
  token_link_cases: {
    name: string;
    provider: GitProvider;
    web_base: string;
    token_name: string;
    description: string;
    owner: string | null;
    repo: string | null;
    expires_in_days: number | null;
    expect: { primary: Link; fallback: Link };
  }[];
  ssh_link_cases: {
    provider: GitProvider;
    web_base: string;
    owner: string | null;
    repo: string | null;
    expect: { user_keys: Link; deploy_key: Link };
  }[];
  scope_cases: {
    provider: GitProvider;
    scopes: string[] | null;
    expect: unknown;
  }[];
};

const vectors = JSON.parse(
  readFileSync(join(CONTRACT, "provider_cases.json"), "utf8"),
) as Vectors;

describe("каталог провайдеров", () => {
  it("копия совпадает с файлом контракта побайтно", () => {
    const copy = readFileSync(join(import.meta.dirname, "providers.json"));
    const origin = readFileSync(join(CONTRACT, "providers.json"));
    expect(copy.equals(origin)).toBe(true);
  });

  it("перечисляет каждого провайдера один раз в порядке перечисления", () => {
    expect(PROVIDER_CATALOG.providers.map((spec) => spec.id)).toEqual([
      ...GIT_PROVIDERS,
    ]);
  });

  it("лимиты github совпадают с документированными", () => {
    expect(providerSpec("github").limits).toEqual({
      name: 40,
      description: 1024,
    });
  });

  it("ни одна ссылка не просит право api", () => {
    for (const spec of PROVIDER_CATALOG.providers) {
      expect(spec.permissions.required).not.toContain("api");
      for (const link of [
        spec.token_links?.primary,
        spec.token_links?.fallback,
      ]) {
        expect(link?.query.map((item) => item.value) ?? []).not.toContain(
          "api",
        );
      }
    }
  });
});

describe("векторы провайдеров", () => {
  it.each(vectors.host_cases.map((c) => [JSON.stringify(c.host), c] as const))(
    "определение по хосту %s",
    (_name, c) => {
      expect(
        detectProvider(c.host, {
          ...(c.overrides ? { overrides: c.overrides } : {}),
          ...(c.api ? { api: c.api } : {}),
        }),
      ).toEqual(c.expect);
    },
  );

  it.each(vectors.web_base_cases.map((c) => [JSON.stringify(c), c] as const))(
    "корень сайта %s",
    (_name, c) => {
      expect(
        webBase({
          host: c.host,
          port: c.port,
          secure: c.secure,
          subpath: c.subpath,
        }),
      ).toBe(c.expect);
    },
  );

  it.each(vectors.api_base_cases.map((c) => [JSON.stringify(c), c] as const))(
    "корень API %s",
    (_name, c) => {
      expect(apiBase(c.provider, c.host, c.web_base)).toBe(c.expect);
    },
  );

  it.each(
    vectors.prefix_cases.map((c) => [JSON.stringify(c.segments), c] as const),
  )("пути установки %s", (_name, c) => {
    expect(instancePrefixCandidates(c.segments)).toEqual(c.expect);
  });

  it.each(
    vectors.text_cases.map((c) => [JSON.stringify(c).slice(0, 80), c] as const),
  )("текст %s", (_name, c) => {
    if (c.kind === "token_name") {
      expect(defaultTokenName(c.project ?? null)).toBe(c.expect);
    } else if (c.kind === "token_description") {
      expect(defaultTokenDescription(c.date ?? "", c.lang ?? "")).toBe(
        c.expect,
      );
    } else if (c.kind === "clean_text") {
      expect(cleanText(c.text ?? "", c.limit ?? 0)).toBe(c.expect);
    } else {
      expect(encodeComponent(c.text ?? "")).toBe(c.expect);
    }
  });

  it.each(vectors.token_link_cases.map((c) => [c.name, c] as const))(
    "ссылки на токен: %s",
    (_name, c) => {
      const links = tokenLinks(c.provider, {
        webBase: c.web_base,
        name: c.token_name,
        description: c.description,
        owner: c.owner,
        repo: c.repo,
        expiresInDays: c.expires_in_days,
      });
      expect({ primary: links.primary, fallback: links.fallback }).toEqual(
        c.expect,
      );
    },
  );

  it.each(
    vectors.ssh_link_cases.map(
      (c) => [`${c.provider} ${c.web_base}`, c] as const,
    ),
  )("ссылки на ключи: %s", (_name, c) => {
    const links = sshLinks(c.provider, {
      webBase: c.web_base,
      owner: c.owner,
      repo: c.repo,
    });
    expect({ user_keys: links.userKeys, deploy_key: links.deployKey }).toEqual(
      c.expect,
    );
  });

  it.each(
    vectors.scope_cases.map(
      (c) => [`${c.provider} ${JSON.stringify(c.scopes)}`, c] as const,
    ),
  )("права токена: %s", (_name, c) => {
    expect(assessScopes(c.provider, c.scopes)).toEqual(c.expect);
  });
});

describe("ссылки", () => {
  it("основная ссылка gitlab просит ровно права git", () => {
    const links = tokenLinks("gitlab", {
      webBase: "https://gitlab.com",
      name: "n",
      description: "d",
    });
    expect(
      links.primary?.url.endsWith("&scopes=read_repository,write_repository"),
    ).toBe(true);
  });

  it("длинное описание режется до лимита github до кодирования", () => {
    const links = tokenLinks("github", {
      webBase: "https://github.com",
      name: "n",
      description: "ab ".repeat(600),
    });
    const description = links.primary?.url
      .split("description=")[1]
      ?.split("&")[0]
      ?.replaceAll("%20", " ");
    expect(Array.from(description ?? "").length).toBeLessThanOrEqual(1024);
  });

  it.each([
    "gitlab.com",
    "ftp://gitlab.com",
    "https://gitlab.com/?x=1",
    "https://git lab.com",
  ])("недопустимый корень сайта %s вызывает ошибку", (base) => {
    expect(() =>
      tokenLinks("gitlab", { webBase: base, name: "n", description: "d" }),
    ).toThrow("webBase");
  });

  it("providerForHost не зависит от регистра и терпит null", () => {
    expect(providerForHost("GitLab.COM")).toBe("gitlab");
    expect(providerForHost(null)).toBe("other");
  });
});
