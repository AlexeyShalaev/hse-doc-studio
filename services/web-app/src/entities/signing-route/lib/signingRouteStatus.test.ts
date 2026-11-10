import { describe, expect, it } from "vitest";
import {
  REMIND_INTERVAL_MS,
  canArchiveRoute,
  canCancelRoute,
  canRemind,
  canReturnForRework,
  canSendRoute,
  isActionable,
  isResend,
  isRouteEditable,
  isRouteLive,
  isRouteOpen,
  nextRemindAt,
  routeSendKind,
  signingPagePath,
  signingPdfUrl,
  signingRouteEditorPath,
} from "./signingRouteStatus";
import type { SigningRouteStatus } from "../model/signingRoute.schema";

const ALL: SigningRouteStatus[] = [
  "draft",
  "active",
  "paused",
  "returned",
  "completed",
  "cancelled",
  "archived",
];
const where = (check: (s: SigningRouteStatus) => boolean) => ALL.filter(check);

describe("статусы маршрута (раздел 5.3)", () => {
  it("незавершённые маршруты точки совпадают с уникальным индексом", () => {
    expect(where(isRouteOpen)).toEqual([
      "draft",
      "active",
      "paused",
      "returned",
    ]);
  });

  it("править и отправлять можно вне активного маршрута", () => {
    expect(where(isRouteEditable)).toEqual([
      "draft",
      "paused",
      "returned",
      "cancelled",
    ]);
    expect(where(canSendRoute)).toEqual(where(isRouteEditable));
    expect(where(isResend)).toEqual(["paused", "returned", "cancelled"]);
  });

  it("отменить можно незавершённый, снять с контроля только завершённый", () => {
    expect(where(canCancelRoute)).toEqual(where(isRouteOpen));
    expect(where(canArchiveRoute)).toEqual(["completed"]);
    expect(where(isRouteLive)).toEqual(["active"]);
  });

  it("вернуть на доработку и напомнить можно только в очередь участника", () => {
    expect(canReturnForRework("to_approve")).toBe(true);
    expect(canReturnForRework("to_sign")).toBe(true);
    expect(canReturnForRework("done")).toBe(false);
    expect(canReturnForRework("waiting")).toBe(false);
    expect(canRemind("invited")).toBe(true);
    expect(canRemind("done")).toBe(false);
  });

  it("действием считаются согласие и подпись", () => {
    expect(isActionable("approve")).toBe(true);
    expect(isActionable("approve_and_sign")).toBe(true);
    expect(isActionable("sign")).toBe(true);
    expect(isActionable("wait")).toBe(false);
    expect(isActionable("done")).toBe(false);
  });

  it("следующее напоминание через 12 часов", () => {
    expect(nextRemindAt(null)).toBeNull();
    expect(nextRemindAt("2026-11-10T09:00:00Z")).toBe(
      Date.parse("2026-11-10T09:00:00Z") + REMIND_INTERVAL_MS,
    );
  });
});

describe("адреса маршрута", () => {
  it("страница подписанта и экран автора", () => {
    expect(signingPagePath("p 1", "sr/1")).toBe("/sign/p%201/sr%2F1");
    expect(signingRouteEditorPath("p1", "topic-approval")).toBe(
      "/projects/p1/submit/cp/topic-approval/route",
    );
  });

  it("PDF задачи: путь бэкенда уже начинается с /api/v1", () => {
    expect(signingPdfUrl("/api/v1/projects/p/docs/d/frozen/pdf")).toMatch(
      /\/api\/v1\/projects\/p\/docs\/d\/frozen\/pdf$/,
    );
  });
});

describe("версия на подписи: какую отправку предлагать (12.6)", () => {
  it("без изменений: черновик отправляют, остановленный отправляют заново", () => {
    expect(ALL.map((s) => [s, routeSendKind(s, [])])).toEqual([
      ["draft", "send"],
      ["active", null],
      ["paused", "resend"],
      ["returned", "resend"],
      ["completed", null],
      ["cancelled", "resend"],
      ["archived", null],
    ]);
  });

  it("с изменениями новая версия откуда угодно, кроме черновика и снятого с контроля", () => {
    expect(where((s) => routeSendKind(s, ["doc"]) === "new_version")).toEqual([
      "active",
      "paused",
      "returned",
      "completed",
      "cancelled",
    ]);
    expect(routeSendKind("draft", ["doc"])).toBe("send");
    expect(routeSendKind("archived", ["doc"])).toBeNull();
  });
});
