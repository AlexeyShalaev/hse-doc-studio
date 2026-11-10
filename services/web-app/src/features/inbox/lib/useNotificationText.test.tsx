import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { beforeEach, describe, expect, it } from "vitest";
import type { Notification } from "@entities/invitation";
import { i18n } from "@shared/lib";
import { useNotificationText } from "./useNotificationText";

const note = (
  kind: Notification["kind"],
  payload: Partial<Notification["payload"]> = {},
): Notification => ({
  id: "n1",
  kind,
  created_at: "2026-11-10T09:00:00Z",
  read_at: null,
  payload: {
    project_id: "p1",
    project_name: "ВКР",
    actor_name: "Иванов И. И.",
    role: null,
    ref_id: "sr_1",
    outcome: null,
    path: null,
    excerpt: "Утверждение темы",
    profile_id: "topic",
    deadline: null,
    ...payload,
  },
});

const textOf = (n: Notification): string => {
  const { result } = renderHook(() => useNotificationText(), {
    wrapper: ({ children }: { children: ReactNode }) => (
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    ),
  });
  return result.current(n);
};

describe("тексты уведомлений о версии на подписи (12.6)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });

  it("запрос раунда новой версии просит подписать новую версию", () => {
    expect(
      textOf(note("signing_request", { new_version: true, outcome: "sign" })),
    ).toBe("Подпишите итоговый PDF новой версии: Утверждение темы");
    expect(
      textOf(
        note("signing_request", { new_version: true, outcome: "approve" }),
      ),
    ).toBe("Иванов И. И. просит согласовать новую версию: Утверждение темы");
    expect(
      textOf(
        note("signing_request", {
          new_version: true,
          outcome: "approve_sign",
        }),
      ),
    ).toBe("Иванов И. И. просит подписать новую версию: Утверждение темы");
  });

  it("обычный запрос и запрос без поля остаются прежними", () => {
    expect(
      textOf(note("signing_request", { new_version: false, outcome: "sign" })),
    ).toBe("Подпишите итоговый PDF: Утверждение темы");
    expect(textOf(note("signing_request", { outcome: "approve" }))).toBe(
      "Иванов И. И. просит согласовать: Утверждение темы",
    );
  });

  it("новая версия тем, чья очередь ещё не настала, и остановка sent_changed", () => {
    expect(textOf(note("signing_new_version"))).toBe(
      "Новая версия на подпись: Утверждение темы. Изменённые документы нужно согласовать заново, запрос придёт в вашу очередь",
    );
    expect(textOf(note("signing_paused", { outcome: "sent_changed" }))).toBe(
      "Версия на подписи изменилась вне маршрута, маршрут остановлен: Утверждение темы. Отправьте новую версию",
    );
  });

  it("по-английски тоже", async () => {
    await i18n.changeLanguage("en");
    expect(
      textOf(
        note("signing_request", { new_version: true, outcome: "approve" }),
      ),
    ).toBe("Иванов И. И. asks you to approve a new version: Утверждение темы");
    expect(textOf(note("signing_new_version"))).toMatch(
      /^A new version is out for signing: Утверждение темы\./,
    );
  });
});
