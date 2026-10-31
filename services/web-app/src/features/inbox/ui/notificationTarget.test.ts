import { describe, expect, it, vi } from "vitest";
import type { Notification } from "@entities/invitation";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

import { notificationTarget } from "./InboxPanel";

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
