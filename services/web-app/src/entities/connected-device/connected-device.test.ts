import { describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import {
  AccountDevicesSchema,
  AI_NEEDS_ACTION,
  DeviceSchema,
  ProjectStudiosSchema,
  StudioLinkSchema,
  commitsText,
  firstUnprovidedEndpoint,
  modelNames,
  presenceDot,
  presenceText,
} from ".";
import {
  NOW,
  makeDevice,
  makeEndpoint,
  makeLink,
  minutesBefore,
} from "./testing";

const t = i18n.getFixedT("ru", "devices");

describe("контракт подключённых Студий", () => {
  it("принимает устройство, ответ проекта, аккаунта и связь локальной Студии", () => {
    expect(() => DeviceSchema.parse(makeDevice())).not.toThrow();
    expect(() =>
      ProjectStudiosSchema.parse({
        online_window_s: 180,
        mine: [makeDevice()],
        others: [{ user_id: "u2", name: "Борис" }],
      }),
    ).not.toThrow();
    expect(() =>
      AccountDevicesSchema.parse({ online_window_s: 180, items: [] }),
    ).not.toThrow();
    expect(() => StudioLinkSchema.parse(makeLink())).not.toThrow();
  });

  it("строгая схема не пропускает лишних полей: например, пути на диске", () => {
    expect(() =>
      DeviceSchema.parse({ ...makeDevice(), folder: "/Users/anna/doc" }),
    ).toThrow();
  });

  it("чужой участник в ответе проекта это только id и имя", () => {
    expect(() =>
      ProjectStudiosSchema.parse({
        online_window_s: 180,
        mine: [],
        others: [{ user_id: "u2", name: "Борис", version: "0.5.0" }],
      }),
    ).toThrow();
  });
});

describe("тексты присутствия", () => {
  it("в сети и «была в сети N минут назад»", () => {
    expect(presenceText(t, makeDevice(), NOW)).toBe("в сети");
    const offline = makeDevice({
      presence: "offline",
      last_seen_at: minutesBefore(5),
    });
    expect(presenceText(t, offline, NOW)).toBe("была в сети 5 минут назад");
    expect(presenceDot(offline)).toBe("offline");
    expect(presenceDot(makeDevice())).toBe("online");
  });

  it("коммиты склоняются, модели сворачиваются счётчиком", () => {
    expect(commitsText(t, 1)).toBe("1 коммит");
    expect(commitsText(t, 3)).toBe("3 коммита");
    expect(commitsText(t, 5)).toBe("5 коммитов");
    expect(modelNames(t, ["a", "b"])).toBe("a, b");
    expect(modelNames(t, ["a", "b", "c", "d", "e"])).toBe("a, b, c и ещё 2");
  });
});

describe("совет по ИИ через Студию", () => {
  it("находит модель без провайдера в облаке", () => {
    expect(firstUnprovidedEndpoint(makeDevice())?.name).toBe("ollama");
    const ready = makeDevice({
      ai: {
        state: "ready",
        endpoints: [makeEndpoint({ state: "ready", provider_name: "Моя" })],
      },
    });
    expect(firstUnprovidedEndpoint(ready)).toBeNull();
  });

  it("у каждого состояния, где нужно действие, есть совет в обоих языках", () => {
    for (const lang of ["ru", "en"] as const) {
      const tr = i18n.getFixedT(lang, "devices");
      for (const state of AI_NEEDS_ACTION) {
        expect(tr(`ai.advice.${state}`)).not.toBe(`ai.advice.${state}`);
      }
    }
  });
});
