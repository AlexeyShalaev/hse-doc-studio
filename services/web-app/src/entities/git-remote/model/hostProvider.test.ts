import { describe, expect, it } from "vitest";
import type { GitHostSettings } from "../api/gitRemoteSchemas";
import { findHostSettings, hostKey, providerOfHost } from "./hostProvider";

const settings = (
  overrides: Partial<GitHostSettings> & { host: string },
): GitHostSettings => ({
  port: null,
  provider_override: null,
  provider_info: { id: "other", detected_by: "unknown", version: null },
  ca_present: false,
  pinned_fingerprint: null,
  ...overrides,
});

describe("hostKey и findHostSettings", () => {
  it("ключ хоста в нижнем регистре, порт через двоеточие", () => {
    expect(hostKey("GitLab.HSE.local", 8443)).toBe("gitlab.hse.local:8443");
    expect(hostKey("github.com", null)).toBe("github.com");
  });

  it("сначала тот же порт, затем запись без порта", () => {
    const list = [
      settings({ host: "git.example.org" }),
      settings({ host: "git.example.org", port: 8443 }),
    ];
    expect(findHostSettings(list, "GIT.example.org", 8443)?.port).toBe(8443);
    expect(findHostSettings(list, "git.example.org", 9000)?.port).toBeNull();
    expect(findHostSettings(list, "other.org", null)).toBeNull();
    expect(findHostSettings(undefined, "git.example.org", null)).toBeNull();
  });
});

describe("providerOfHost", () => {
  it("без настроек провайдера даёт имя хоста", () => {
    expect(providerOfHost("gitlab.com", null, undefined)).toEqual({
      id: "gitlab",
      detected_by: "host",
      version: null,
    });
    expect(providerOfHost("git.corp.example", null, [])).toEqual({
      id: "other",
      detected_by: "unknown",
      version: null,
    });
    expect(providerOfHost(null, null, [])).toMatchObject({ id: "other" });
  });

  it("выбор человека сильнее имени хоста и берёт версию того же провайдера", () => {
    const list = [
      settings({
        host: "github.company.org",
        provider_override: "gitlab",
        provider_info: {
          id: "gitlab",
          detected_by: "override",
          version: "17.3.1",
        },
      }),
    ];
    expect(providerOfHost("github.company.org", null, list)).toEqual({
      id: "gitlab",
      detected_by: "override",
      version: "17.3.1",
    });
  });

  it("версия чужого провайдера не переносится на выбранного", () => {
    const list = [
      settings({
        host: "git.x.org",
        provider_override: "gitea",
        provider_info: { id: "gitlab", detected_by: "api", version: "16.0.0" },
      }),
    ];
    expect(providerOfHost("git.x.org", null, list).version).toBeNull();
  });

  it("ответ API сервера берётся, когда по имени хоста не узнать", () => {
    const known = { id: "gitlab", detected_by: "api", version: "13.12.0" };
    expect(providerOfHost("git.corp.example", null, [], known)).toEqual(known);
    const saved = [
      settings({ host: "git.corp.example", provider_info: known }),
    ];
    expect(providerOfHost("git.corp.example", null, saved)).toEqual(known);
  });

  it("версию по имени хоста берёт из ответа сервера того же провайдера", () => {
    const known = { id: "gitlab", detected_by: "host", version: "17.3.1" };
    expect(providerOfHost("gitlab.hse.local", null, [], known).version).toBe(
      "17.3.1",
    );
  });

  it("незнакомые значения от сервера не ломают показ", () => {
    const known = { id: "from_future", detected_by: "api", version: null };
    expect(providerOfHost("git.corp.example", null, [], known).id).toBe(
      "other",
    );
  });
});
