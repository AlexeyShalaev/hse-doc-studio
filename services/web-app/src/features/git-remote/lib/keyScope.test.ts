import { afterEach, describe, expect, it } from "vitest";
import type { GitCredential } from "@entities/git-remote";
import { i18n } from "@shared/lib/i18n";
import { SSH_KEY } from "../testing/connectFixtures";
import {
  deployKeyLabel,
  deployKeyRepo,
  deployKeysOf,
  isDeployKey,
  repoPathOf,
  userKeysOf,
} from "./keyScope";
import { parseRemoteUrl } from "./parseRemoteUrl";

const key = (id: string, label: string): GitCredential => ({
  ...SSH_KEY,
  id,
  label,
});

describe("keyScope", () => {
  afterEach(async () => {
    await i18n.changeLanguage("ru");
  });

  it("название deploy-ключа несёт репозиторий и узнаётся на обоих языках", async () => {
    expect(deployKeyLabel("hse-team/paper")).toBe(
      "Deploy-ключ: hse-team/paper",
    );
    await i18n.changeLanguage("en");
    const english = deployKeyLabel("hse-team/paper");
    expect(english).toBe("Deploy key: hse-team/paper");
    await i18n.changeLanguage("ru");
    // Ключ, созданный в английской локали, узнаётся в русской.
    const created = key("k1", english);
    expect(isDeployKey(created)).toBe(true);
    expect(deployKeyRepo(created)).toBe("hse-team/paper");
  });

  it("ключ пользователя не считается deploy-ключом", () => {
    expect(isDeployKey(key("u", "Ключ: GitHub, github.com"))).toBe(false);
    expect(deployKeyRepo(key("u", "Ключ: GitHub, github.com"))).toBeNull();
  });

  it("deploy-ключи берутся только для своего репозитория, без учёта регистра", () => {
    const keys = [
      key("u", "Ключ: GitHub, github.com"),
      key("d1", "Deploy-ключ: hse-team/paper"),
      key("d2", "Deploy-ключ: hse-team/other"),
      key("d3", "Deploy key: HSE-Team/Paper"),
    ];
    expect(deployKeysOf(keys, "hse-team/paper").map((item) => item.id)).toEqual(
      ["d1", "d3"],
    );
    expect(userKeysOf(keys).map((item) => item.id)).toEqual(["u"]);
  });

  it("путь репозитория берётся из адреса", () => {
    const parsed = parseRemoteUrl("https://github.com/hse-team/paper.git");
    expect(parsed.ok && repoPathOf(parsed.url)).toBe("hse-team/paper");
  });
});
