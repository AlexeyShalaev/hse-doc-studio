import { describe, expect, it, vi } from "vitest";
import type { Notification } from "@entities/invitation";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

import {
  notificationRoute,
  notificationTarget,
  popoverAction,
} from "./notificationTarget";

const note = (
  kind: Notification["kind"],
  payload: Partial<Notification["payload"]>,
): Notification => ({
  id: "n1",
  kind,
  created_at: "2026-11-03T09:00:00Z",
  read_at: null,
  payload: {
    project_id: "p1",
    project_name: "ВКР",
    actor_name: "Рита",
    role: null,
    ref_id: null,
    outcome: null,
    path: null,
    excerpt: null,
    profile_id: null,
    deadline: null,
    new_version: false,
    freed_bytes: null,
    ...payload,
  },
});

describe("notificationTarget", () => {
  it("opens the file and the thread for a review notification", () => {
    expect(
      notificationTarget(
        note("review_mention", { path: "chapters/a b.tex", ref_id: "rvt_1" }),
      ),
    ).toBe("/projects/p1/files?file=chapters%2Fa+b.tex&thread=rvt_1");
  });

  it("opens the project for everything else", () => {
    expect(notificationTarget(note("project_invitation", {}))).toBe(
      "/projects/p1",
    );
    expect(notificationTarget(note("review_thread", { path: null }))).toBe(
      "/projects/p1",
    );
  });
});

describe("popoverAction", () => {
  it("непрочитанное приглашение ведёт на «Входящие» и отмечается прочитанным", () => {
    expect(popoverAction(note("project_invitation", {}))).toEqual({
      route: "/inbox",
      markRead: true,
    });
  });

  it("непрочитанный запрос доступа остаётся непрочитанным до решения", () => {
    expect(popoverAction(note("access_request", {}))).toEqual({
      route: "/inbox",
      markRead: false,
    });
  });

  it("обычное уведомление открывает свою цель и отмечается", () => {
    expect(
      popoverAction(note("review_reply", { path: "a.tex", ref_id: "t1" })),
    ).toEqual({
      route: "/projects/p1/files?file=a.tex&thread=t1",
      markRead: true,
    });
  });

  it("прочитанное не отмечается заново, приглашение ведёт в проект", () => {
    expect(
      popoverAction({
        ...note("project_invitation", {}),
        read_at: "2026-11-03T10:00:00Z",
      }),
    ).toEqual({ route: "/projects/p1", markRead: false });
  });

  it("админские уведомления ведут в админку, «вас убрали» никуда", () => {
    expect(popoverAction(note("backup_failed", {})).route).toBe(
      "/admin/backups",
    );
    expect(
      popoverAction(note("system_alert", { outcome: "diag_fail" })).route,
    ).toBe("/admin/diagnostics");
    expect(popoverAction(note("member_removed", {})).route).toBeNull();
  });
});

describe("маршрут подписания", () => {
  const signing = (kind: Notification["kind"]) =>
    note(kind, {
      project_id: "p 1",
      ref_id: "sr_1",
      profile_id: "topic-approval",
      excerpt: "Заявка на тему КП",
    });

  it("запрос, напоминание и новая версия ведут подписанта на его страницу", () => {
    expect(notificationRoute(signing("signing_request"))).toBe(
      "/sign/p%201/sr_1",
    );
    expect(notificationRoute(signing("signing_reminder"))).toBe(
      "/sign/p%201/sr_1",
    );
    expect(notificationRoute(signing("signing_new_version"))).toBe(
      "/sign/p%201/sr_1",
    );
    expect(popoverAction(signing("signing_new_version"))).toEqual({
      route: "/sign/p%201/sr_1",
      markRead: true,
    });
  });

  it("остановка из-за подмены версии на подписи ведёт к карточке «Подписание»", () => {
    expect(
      notificationRoute(
        note("signing_paused", {
          project_id: "p 1",
          ref_id: "sr_1",
          profile_id: "topic-approval",
          outcome: "sent_changed",
        }),
      ),
    ).toBe("/projects/p%201/submit/cp/topic-approval#signing-route");
  });

  it("возврат, остановка, завершение и отмена ведут к карточке на точке сдачи", () => {
    for (const kind of [
      "signing_returned",
      "signing_paused",
      "signing_completed",
      "signing_cancelled",
    ] as const) {
      expect(notificationRoute(signing(kind))).toBe(
        "/projects/p%201/submit/cp/topic-approval#signing-route",
      );
    }
  });

  it("без маршрута или точки ведёт в проект, без проекта никуда", () => {
    expect(
      notificationRoute(
        note("signing_request", { ref_id: null, profile_id: null }),
      ),
    ).toBe("/projects/p1");
    expect(
      notificationRoute(note("signing_completed", { project_id: null })),
    ).toBeNull();
  });

  it("в окошке запрос открывает страницу подписи и отмечается прочитанным", () => {
    expect(popoverAction(signing("signing_request"))).toEqual({
      route: "/sign/p%201/sr_1",
      markRead: true,
    });
  });
});

describe("очистка диска раннера администратором (storage-cleanup.md, 8.2)", () => {
  it("ведёт в «Мои раннеры» с открытым «Диском» раннера и отмечается прочитанным", () => {
    const n = note("runner_disk_cleaned", {
      project_id: null,
      project_name: null,
      ref_id: "rn 1",
      excerpt: "Домашний сервер",
      outcome: "done",
      freed_bytes: 1024,
    });
    expect(notificationRoute(n)).toBe("/settings/runners?disk=rn+1");
    expect(popoverAction(n)).toEqual({
      route: "/settings/runners?disk=rn+1",
      markRead: true,
    });
  });

  it("без id раннера просто «Мои раннеры»", () => {
    expect(
      notificationRoute(
        note("runner_disk_cleaned", { project_id: null, ref_id: null }),
      ),
    ).toBe("/settings/runners");
  });
});
