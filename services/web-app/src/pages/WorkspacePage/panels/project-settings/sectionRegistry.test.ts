import { describe, expect, it } from "vitest";
import {
  groupSections,
  resolveProjectSettingsGroup,
  visibleProjectSettingsGroups,
  visibleProjectSettingsSections,
  type ProjectSettingsSectionContext,
} from "./sectionRegistry";

const ctx = (
  overrides: Partial<ProjectSettingsSectionContext> = {},
): ProjectSettingsSectionContext => ({
  isTeam: false,
  hasDocFormats: false,
  hasDocSetMeta: false,
  hasMetaFields: false,
  syncSupported: true,
  syncConnected: false,
  hasSharedFolder: false,
  ...overrides,
});

const ids = (value: { id: string }[]): string[] => value.map((v) => v.id);

describe("группа «Синхронизация» в настройках проекта", () => {
  it("видна, когда бэкенд умеет синхронизацию, даже без репозитория", () => {
    expect(ids(visibleProjectSettingsGroups(ctx()))).toContain("sync");
  });

  it("без репозитория показывает подключение, обмен файлом и автосборку", () => {
    const group = resolveProjectSettingsGroup("sync", ctx());
    expect(ids(groupSections(group, ctx()))).toEqual([
      "sync-remote",
      "sync-exchange",
      "sync-ci",
    ]);
  });

  it("с репозиторием добавляет фоновую проверку", () => {
    const connected = ctx({ syncConnected: true });
    const group = resolveProjectSettingsGroup("sync", connected);
    expect(ids(groupSections(group, connected))).toEqual([
      "sync-remote",
      "sync-options",
      "sync-exchange",
      "sync-ci",
    ]);
  });

  it("папку в облачном диске показывает только при её обнаружении", () => {
    const shared = ctx({ syncConnected: true, hasSharedFolder: true });
    const group = resolveProjectSettingsGroup("sync", shared);
    expect(ids(groupSections(group, shared))).toEqual([
      "sync-remote",
      "sync-options",
      "sync-shared-folder",
      "sync-exchange",
      "sync-ci",
    ]);
  });

  it("обнаруженная папка без подключённого репозитория не открывает карточку", () => {
    const odd = ctx({ hasSharedFolder: true });
    expect(ids(visibleProjectSettingsSections(odd))).not.toContain(
      "sync-shared-folder",
    );
  });

  it("на старом бэкенде группа и все её разделы скрыты", () => {
    const old = ctx({
      syncSupported: false,
      syncConnected: true,
      hasSharedFolder: true,
    });
    expect(ids(visibleProjectSettingsGroups(old))).not.toContain("sync");
    expect(ids(visibleProjectSettingsSections(old))).not.toEqual(
      expect.arrayContaining(["sync-remote"]),
    );
    expect(ids(visibleProjectSettingsSections(old))).not.toContain(
      "sync-exchange",
    );
    expect(ids(visibleProjectSettingsSections(old))).not.toContain("sync-ci");
  });

  it("ссылка на группу и ссылка на раздел ведут на одну страницу", () => {
    const connected = ctx({ syncConnected: true });
    expect(resolveProjectSettingsGroup("sync", connected).id).toBe("sync");
    expect(resolveProjectSettingsGroup("sync-options", connected).id).toBe(
      "sync",
    );
  });

  it("ссылка на недоступный раздел открывает его группу, а без группы возвращает «Проект»", () => {
    // Репозитория нет, но группа есть: человек увидит карточку подключения.
    const group = resolveProjectSettingsGroup("sync-options", ctx());
    expect(group.id).toBe("sync");
    expect(ids(groupSections(group, ctx()))).toEqual([
      "sync-remote",
      "sync-exchange",
      "sync-ci",
    ]);
    const old = ctx({ syncSupported: false });
    expect(resolveProjectSettingsGroup("sync", old).id).toBe("project");
    expect(resolveProjectSettingsGroup("sync-remote", old).id).toBe("project");
  });

  it("прежние группы остаются на своих местах", () => {
    expect(ids(visibleProjectSettingsGroups(ctx()))).toEqual([
      "project",
      "people",
      "documents",
      "checks",
      "sync",
    ]);
    expect(resolveProjectSettingsGroup("fonts", ctx()).id).toBe("documents");
  });
});
