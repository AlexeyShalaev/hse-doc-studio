import { describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { SETTINGS_SEARCH_INDEX } from "./searchIndex";

const profileEntries = SETTINGS_SEARCH_INDEX.filter(
  (entry) => entry.sectionId === "profile",
);

describe("settings search index: author profile", () => {
  it("registers the section, name and e-mail anchors", () => {
    expect(profileEntries.map((e) => e.anchorId)).toEqual([
      "profile",
      "profile-name",
      "profile-email",
    ]);
  });

  it.each(["ru", "en"])("has a label in %s for every entry", async (lang) => {
    await i18n.changeLanguage(lang);
    for (const entry of profileEntries) {
      const label = i18n.t(entry.labelKey, { ns: "settings" });
      expect(label).not.toBe(entry.labelKey);
      expect(label.length).toBeGreaterThan(2);
    }
  });

  it("is found by Russian and English words regardless of the interface language", () => {
    const find = (word: string) =>
      profileEntries.some((e) =>
        (e.keywords ?? []).some((k) => k.toLowerCase().includes(word)),
      );
    for (const word of ["автор", "почта", "имя", "author", "email", "commit"]) {
      expect(find(word)).toBe(true);
    }
  });

  it("keeps every anchor id unique across the whole index", () => {
    const ids = SETTINGS_SEARCH_INDEX.map((e) => e.anchorId);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

const accessEntries = SETTINGS_SEARCH_INDEX.filter(
  (entry) => entry.sectionId === "git-access",
);

describe("settings search index: repository access", () => {
  it("registers the section and every block anchor", () => {
    expect(accessEntries.map((e) => e.anchorId)).toEqual([
      "git-access",
      "git-access-credentials",
      "git-access-hosts",
      "git-access-encryption",
      "git-access-fetch",
    ]);
  });

  it.each(["ru", "en"])("has a label in %s for every entry", async (lang) => {
    await i18n.changeLanguage(lang);
    for (const entry of accessEntries) {
      const label = i18n.t(entry.labelKey, { ns: "settings" });
      expect(label).not.toBe(entry.labelKey);
      expect(label.length).toBeGreaterThan(2);
    }
  });

  it("is found by Russian and English words regardless of the interface language", () => {
    const find = (word: string) =>
      accessEntries.some((e) =>
        (e.keywords ?? []).some((k) => k.toLowerCase().includes(word)),
      );
    for (const word of [
      "токен",
      "ключ",
      "отпечаток",
      "token",
      "fingerprint",
      "ssh",
    ]) {
      expect(find(word)).toBe(true);
    }
  });
});
