import { describe, expect, it } from "vitest";
import type { SigningRoute } from "@entities/signing-route";
import {
  SIGNING_ROUTE_CONTRACT_EXAMPLES,
  SR_AUTHOR,
  SR_DOC,
  SR_REVIEW_DOC,
  makeRouteParticipant,
  makeSigningRoute,
} from "@entities/signing-route/testing";
import { newVersionSummary, routeVersionView } from "./routeVersion";

const route = (name: string): SigningRoute =>
  SIGNING_ROUTE_CONTRACT_EXAMPLES.SigningRoute?.[name] as SigningRoute;
const preview = (name: string) =>
  SIGNING_ROUTE_CONTRACT_EXAMPLES.SigningRoutePreview?.[name] as Parameters<
    typeof newVersionSummary
  >[1];
const docName = (doc: { doc_id: string; name: Record<string, string> }) =>
  doc.name.ru ?? doc.doc_id;

describe("версия на подписи в карточке (12.2)", () => {
  it("маршрут без изменений: версия есть, изменений нет", () => {
    const view = routeVersionView(makeSigningRoute());
    expect(view.docs.map((d) => d.doc_id)).toEqual([SR_DOC.doc_id]);
    expect(view.changed).toEqual([]);
    expect(view.sentAt).toBe("2026-11-10T09:00:00Z");
    expect(view.lost).toBe(false);
  });

  it("рабочая сборка ушла вперёд: изменившийся документ и дата его версии", () => {
    const view = routeVersionView(route("diverged"));
    expect(view.changed.map((d) => d.doc_id)).toEqual([SR_DOC.doc_id]);
    expect(view.sentAt).toBe("2026-11-10T09:00:00Z");
    expect(view.lost).toBe(false);
  });

  it("дата версии берётся у изменившихся документов", () => {
    const base = route("new_version");
    const view = routeVersionView({
      ...base,
      docs: base.docs.map((doc) =>
        doc.doc_id === SR_REVIEW_DOC.doc_id ? { ...doc, changed: true } : doc,
      ),
    });
    expect(view.changed.map((d) => d.doc_id)).toEqual([SR_REVIEW_DOC.doc_id]);
    expect(view.sentAt).toBe("2026-11-10T09:00:00Z");
    // Без изменений: самая поздняя версия маршрута.
    expect(routeVersionView(base).sentAt).toBe("2026-11-12T10:30:00Z");
  });

  it("завершённый с правкой после подписания", () => {
    const view = routeVersionView(route("completed_changed"));
    expect(view.changed).toHaveLength(1);
    expect(view.lost).toBe(false);
  });

  it("перенос 0.20.0 не нашёл версию: восстановить нельзя", () => {
    const view = routeVersionView(route("migration_lost"));
    expect(view.lost).toBe(true);
    expect(view.sentAt).toBeNull();
    expect(view.docs.map((d) => d.doc_id)).toEqual([SR_DOC.doc_id]);
  });

  it("сервер до R16 полей не отдаёт: ничего не менялось", () => {
    const { changed_docs: _changed, ...base } = makeSigningRoute({
      status: "paused",
      stop_reason: "sent_changed",
    });
    const old = {
      ...base,
      docs: base.docs.map(({ sent: _s, changed: _c, ...doc }) => doc),
    } as SigningRoute;
    expect(routeVersionView(old)).toEqual({
      docs: [],
      changed: [],
      sentAt: null,
      lost: false,
    });
  });
});

describe("подтверждение новой версии (12.6)", () => {
  it("изменились, без изменений и кто согласует заново", () => {
    // Научрук согласовал прежнюю версию, его согласие не переносится; автор согласует отправкой.
    const base = route("new_version");
    const approved = {
      ...base,
      steps: base.steps.map((step) =>
        step.map((p) =>
          p.id === "srp_supervisor"
            ? { ...p, approved_at: "2026-11-11T09:00:00Z" }
            : p,
        ),
      ),
    };
    const summary = newVersionSummary(
      approved,
      preview("new_version"),
      SR_AUTHOR.id,
      docName,
    );
    expect(summary.changed).toEqual(["Заявление о выборе темы"]);
    expect(summary.kept).toEqual(["Отзыв руководителя"]);
    expect(summary.reapprove.map((p) => p.id)).toEqual(["srp_supervisor"]);
  });

  it("ещё не согласовавший и сам отправитель в «согласуют заново» не попадают", () => {
    const summary = newVersionSummary(
      route("new_version"),
      preview("new_version"),
      SR_AUTHOR.id,
      docName,
    );
    expect(summary.reapprove).toEqual([]);
  });

  it("до R16 изменившиеся документы из маршрута, людей не перечисляем", () => {
    const diverged = route("diverged");
    const base = preview("new_version");
    const old = {
      ...base,
      docs: base.docs.map(({ change: _c, sent: _s, ...doc }) => doc),
      participants: base.participants.map(
        ({ keeps_approval: _k, ...p }) => p,
      ),
    };
    const summary = newVersionSummary(
      {
        ...diverged,
        steps: [[makeRouteParticipant({ user_id: "u_other" })]],
      },
      old,
      SR_AUTHOR.id,
      docName,
    );
    expect(summary.changed).toEqual(["Заявление о выборе темы"]);
    expect(summary.kept).toEqual(["Отзыв руководителя"]);
    expect(summary.reapprove).toEqual([]);
  });
});
