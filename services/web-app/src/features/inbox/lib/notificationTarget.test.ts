import { describe, expect, it, vi } from "vitest";
import type { Notification } from "@entities/invitation";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

import { notificationTarget, popoverAction } from "./notificationTarget";

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
