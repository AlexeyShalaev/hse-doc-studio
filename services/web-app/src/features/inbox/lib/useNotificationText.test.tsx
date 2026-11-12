import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { beforeEach, describe, expect, it } from "vitest";
import type { Notification } from "@entities/invitation";
import { i18n } from "@shared/lib";
import {
  useNotificationDetails,
  useNotificationText,
} from "./useNotificationText";

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
    doc_id: null,
    profile_id: "topic",
    deadline: null,
    new_version: false,
    freed_bytes: null,
    ...payload,
  },
});

const wrapper = ({ children }: { children: ReactNode }) => (
  <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
);

const detailsOf = (n: Notification): string | null =>
  renderHook(() => useNotificationDetails(), { wrapper }).result.current(n);

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
          freed_bytes: null,
          outcome: "approve_sign",
        }),
      ),
    ).toBe("Иванов И. И. просит подписать новую версию: Утверждение темы");
  });

  it("обычный запрос (new_version false) остаётся прежним", () => {
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

const GIB = 1024 ** 3;
const disk = (payload: Partial<Notification["payload"]>): Notification =>
  note("runner_disk_cleaned", {
    project_id: null,
    project_name: null,
    actor_name: "Алексей Шалаев",
    ref_id: "rn_1",
    excerpt: "Домашний сервер",
    doc_id: null,
    profile_id: null,
    outcome: "done",
    freed_bytes: 12.5 * GIB,
    ...payload,
  });

describe("очистка диска раннера администратором (storage-cleanup.md, 8.2)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });

  it("итог по состоянию команды и освобождённый размер", () => {
    expect(textOf(disk({}))).toBe(
      "Администратор очистил диск вашего раннера «Домашний сервер»: освобождено 12.50 GB",
    );
    expect(textOf(disk({ freed_bytes: 0 }))).toBe(
      "Администратор очистил диск вашего раннера «Домашний сервер»: освобождать было нечего",
    );
    expect(
      textOf(disk({ outcome: "error", freed_bytes: 300 * 1024 ** 2 })),
    ).toBe(
      "Администратор очистил диск вашего раннера «Домашний сервер», очистка завершилась с ошибками: освобождено 300 MB",
    );
    expect(textOf(disk({ outcome: "cancelled", freed_bytes: 0 }))).toBe(
      "Очистку диска вашего раннера «Домашний сервер», которую запустил администратор, остановили: освобождено 0 MB",
    );
    expect(textOf(disk({ outcome: "lost" }))).toMatch(
      /^Раннер «Домашний сервер» пропал во время очистки диска/,
    );
  });

  it("под текстом администратор, который запустил очистку; без имени ничего", () => {
    expect(detailsOf(disk({}))).toBe("Запустил администратор Алексей Шалаев");
    expect(detailsOf(disk({ actor_name: null }))).toBeNull();
  });

  it("по-английски тоже", async () => {
    await i18n.changeLanguage("en");
    expect(textOf(disk({}))).toBe(
      "An administrator cleaned up the disk of your runner “Домашний сервер”: 12.50 GB freed",
    );
  });
});
