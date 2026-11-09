import type { ReactNode } from "react";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import {
  SR_AUTHOR,
  SR_DOC,
  SR_PROJECT_ID,
  SR_SUPERVISOR,
  makeRouteEvent,
  makeSigningTask,
} from "@entities/signing-route/testing";
import type {
  SigningTask,
  SigningTaskDoc,
  SigningTaskMe,
  SigningTaskPerson,
  SigningTaskSlot,
} from "@entities/signing-route";
import type { SigningPageState } from "../model/useSigningPage";
import { galleryPdfUrl } from "./galleryPdf";
import { SigningView, type SigningViewProps } from "./SigningView";

// Галерея страницы подписанта: «Заявка на тему КП», автор картинкой, научрук открепленной
// ЭП, академрук картинкой. PDF настоящий (образец), рамки «Ваша подпись» на своих местах.

const ACADEMIC = "Сидоров С. С.";
const BUILD = `build:${"3f".repeat(32)}`;
// Галерея показывает срок как ещё не наступивший.
const BEFORE_DEADLINE = Date.parse("2026-11-12T10:00:00Z");

const person = (
  name: string,
  persona: string,
  state: SigningTaskPerson["state"],
  extra: Partial<SigningTaskPerson> = {},
): SigningTaskPerson => ({
  name,
  persona,
  state,
  at: null,
  me: false,
  ...extra,
});

const SENT = "2026-11-10T09:00:00Z";
const APPROVED = "2026-11-11T14:20:00Z";

const slot = (
  slotId: "author" | "supervisor" | "academic_supervisor",
  overrides: Partial<SigningTaskSlot> = {},
): SigningTaskSlot => {
  const base = {
    author: {
      label: { ru: "Студент", en: "Student" },
      x_mm: 120,
      y_mm: 230,
      mark: "png" as const,
    },
    supervisor: {
      label: { ru: "Научный руководитель", en: "Supervisor" },
      x_mm: 110,
      y_mm: 130,
      mark: "plate" as const,
    },
    academic_supervisor: {
      label: { ru: "Академический руководитель", en: "Academic supervisor" },
      x_mm: 110,
      y_mm: 160,
      mark: "png" as const,
    },
  }[slotId];
  return {
    slot_id: slotId,
    page: 1,
    width_mm: 40,
    status: "pending",
    reason: "awaiting_approval",
    ...base,
    ...overrides,
  };
};

const doc = (overrides: Partial<SigningTaskDoc> = {}): SigningTaskDoc => ({
  ...SR_DOC,
  pdf_url: `/api/v1/projects/${SR_PROJECT_ID}/docs/${SR_DOC.doc_id}/pdf/signed`,
  frozen: false,
  token: BUILD,
  mine: [slot("supervisor")],
  others: [
    {
      slot_id: "author",
      label: { ru: "Студент", en: "Student" },
      page: 1,
      status: "signed",
    },
    {
      slot_id: "academic_supervisor",
      label: { ru: "Академический руководитель", en: "Academic supervisor" },
      page: 1,
      status: "pending",
    },
  ],
  ...overrides,
});

const supervisorMe = (
  overrides: Partial<SigningTaskMe> = {},
): SigningTaskMe => ({
  participant_id: "srp_supervisor",
  state: "to_approve",
  next_action: "approve",
  methods: ["image", "detached"],
  method: "detached",
  image_ready: false,
  plate: {
    owner: SR_SUPERVISOR.name,
    kind: "openpgp",
    cert_id: "1A2B 3C4D 5E6F 7A8B",
  },
  keys: { server_keys_allowed: false, default_key: null },
  ...overrides,
});

/** Научрук на шаге 2 из 3, фаза согласования: «Согласовать». */
const supervisorTurn = (overrides: Partial<SigningTask> = {}): SigningTask =>
  makeSigningTask({
    route: {
      ...makeSigningTask().route,
      phase: "approval",
      current_step: 2,
    },
    steps: [
      [person(SR_AUTHOR.name, "author", "done", { at: SENT })],
      [person(SR_SUPERVISOR.name, "supervisor", "to_approve", { me: true })],
      [person(ACADEMIC, "academic_supervisor", "waiting")],
    ],
    me: supervisorMe(),
    docs: [doc()],
    events: [makeRouteEvent({ at: SENT })],
    ...overrides,
  });

/** Академрук на шаге 3: картинкой. */
const academicTask = (
  state: SigningTaskPerson["state"],
  overrides: Partial<SigningTask> = {},
): SigningTask =>
  makeSigningTask({
    route: {
      ...makeSigningTask().route,
      phase: "approval",
      current_step: state === "waiting" ? 2 : 3,
    },
    steps: [
      [person(SR_AUTHOR.name, "author", "done", { at: SENT })],
      [
        state === "waiting"
          ? person(SR_SUPERVISOR.name, "supervisor", "to_approve")
          : person(SR_SUPERVISOR.name, "supervisor", "waiting", {
              at: APPROVED,
            }),
      ],
      [person(ACADEMIC, "academic_supervisor", state, { me: true })],
    ],
    me: supervisorMe({
      participant_id: "srp_academic",
      state,
      next_action: state === "to_approve" ? "approve" : "wait",
      methods: ["image", "detached"],
      method: "image",
      image_ready: false,
      plate: null,
    }),
    docs: [
      doc({
        mine: [slot("academic_supervisor")],
        others: [
          {
            slot_id: "author",
            label: { ru: "Студент", en: "Student" },
            page: 1,
            status: "signed",
          },
          {
            slot_id: "supervisor",
            label: { ru: "Научный руководитель", en: "Supervisor" },
            page: 1,
            status: "pending",
          },
        ],
      }),
    ],
    events: [
      makeRouteEvent({ at: SENT }),
      ...(state === "waiting"
        ? []
        : [
            makeRouteEvent({
              id: "sre_02",
              kind: "approved",
              at: APPROVED,
              who: SR_SUPERVISOR.name,
            }),
          ]),
    ],
    ...overrides,
  });

const route = (patch: Partial<SigningTask["route"]>) => ({
  ...supervisorTurn().route,
  ...patch,
});

const ready = (task: SigningTask): SigningPageState => ({
  kind: "ready",
  task,
});

const noop = () => undefined;

const view = (
  state: SigningPageState,
  extra: Partial<SigningViewProps> = {},
) => (
  <div style={{ height: 980, display: "flex", flexDirection: "column" }}>
    <SigningView
      state={state}
      now={BEFORE_DEADLINE}
      onApprove={noop}
      onReturn={() => Promise.resolve(true)}
      onRetry={noop}
      pdfUrlOf={galleryPdfUrl}
      {...extra}
    />
  </div>
);

const entry = (
  id: string,
  title: string,
  render: () => ReactNode,
  note?: string,
): GalleryEntry => ({
  id,
  title,
  frame: "window",
  width: 1120,
  render,
  ...(note ? { note } : {}),
});

const RETURN_COMMENT = "Уточните цель проекта во втором абзаце.";

/** Страница подписанта /sign/:projectId/:routeId (срез W4). */
export const getSigningPageGallery = (): GalleryGroup[] => [
  {
    id: "signing-turn",
    title: "Подписант: его очередь",
    description:
      "Шапка, ход маршрута, что нужно, PDF с рамкой «Ваша подпись», кнопки. На телефоне кнопки прилипают к низу экрана.",
    entries: [
      entry(
        "signing_turn_approve",
        "Согласовать: ключ для плашки известен",
        () => view(ready(supervisorTurn())),
      ),
      entry(
        "signing_turn_image_missing",
        "Согласовать картинкой: картинки ещё нет",
        () => view(ready(academicTask("to_approve"))),
        "Кнопка ждёт картинку; место блока загрузки (срез W5) отмечено заглушкой.",
      ),
      entry(
        "signing_turn_approve_sign",
        "Согласовать и подписать (документы зафиксированы)",
        () =>
          view(
            ready(
              makeSigningTask({
                steps: [
                  [person(SR_AUTHOR.name, "author", "done", { at: SENT })],
                  [
                    person(
                      SR_SUPERVISOR.name,
                      "supervisor",
                      "to_approve_sign",
                      { me: true },
                    ),
                  ],
                ],
              }),
            ),
          ),
        "Главная кнопка и блок ЭП появятся в срезе W5.",
      ),
      entry("signing_turn_sign", "Подписать итоговый PDF", () =>
        view(
          ready(
            supervisorTurn({
              route: route({ phase: "signing", current_step: 3 }),
              steps: [
                [person(SR_AUTHOR.name, "author", "done", { at: SENT })],
                [
                  person(SR_SUPERVISOR.name, "supervisor", "to_sign", {
                    me: true,
                    at: APPROVED,
                  }),
                ],
                [
                  person(ACADEMIC, "academic_supervisor", "done", {
                    at: "2026-11-12T08:00:00Z",
                  }),
                ],
              ],
              me: supervisorMe({
                state: "to_sign",
                next_action: "sign",
                methods: ["detached"],
              }),
              docs: [
                doc({
                  frozen: true,
                  pdf_url: `/api/v1/projects/${SR_PROJECT_ID}/docs/${SR_DOC.doc_id}/frozen/pdf`,
                  token: `pdf:${"9c".repeat(32)}`,
                  mine: [slot("supervisor", { reason: "no_signature_file" })],
                }),
              ],
            }),
          ),
        ),
      ),
      entry("signing_turn_resent", "Отправлено заново после пересборки", () =>
        view(
          ready(
            supervisorTurn({
              route: route({ round: 2 }),
              events: [
                makeRouteEvent({ at: SENT }),
                makeRouteEvent({
                  id: "sre_02",
                  kind: "approved",
                  at: APPROVED,
                  who: SR_SUPERVISOR.name,
                }),
                makeRouteEvent({
                  id: "sre_03",
                  kind: "paused",
                  at: "2026-11-11T16:00:00Z",
                  who: null,
                  reason: "rebuilt",
                }),
                makeRouteEvent({
                  id: "sre_04",
                  kind: "resumed",
                  round: 2,
                  at: "2026-11-11T18:30:00Z",
                }),
              ],
            }),
          ),
        ),
      ),
      entry("signing_turn_two_docs", "Два документа вкладками", () =>
        view(
          ready(
            supervisorTurn({
              docs: [
                doc(),
                doc({
                  doc_id: "approval_sheet",
                  name: { ru: "Лист согласования", en: "Approval sheet" },
                  mine: [
                    slot("supervisor"),
                    slot("supervisor", {
                      slot_id: "supervisor_2",
                      page: 1,
                      y_mm: 230,
                      x_mm: 120,
                    }),
                  ],
                }),
              ],
            }),
          ),
        ),
      ),
      entry(
        "signing_turn_overdue_failure",
        "Срок прошёл, документ изменился при согласовании",
        () =>
          view(ready(supervisorTurn()), {
            now: Date.parse("2026-11-16T09:00:00Z"),
            failure: "doc_changed",
            onDismissFailure: noop,
          }),
      ),
    ],
  },
  {
    id: "signing-wait",
    title: "Подписант: ждёт или уже сделал",
    entries: [
      entry("signing_not_yet", "Пока не его очередь", () =>
        view(ready(academicTask("waiting"))),
      ),
      entry("signing_approved", "Согласовал, ждёт итоговый PDF", () =>
        view(
          ready(
            supervisorTurn({
              steps: [
                [person(SR_AUTHOR.name, "author", "done", { at: SENT })],
                [
                  person(SR_SUPERVISOR.name, "supervisor", "waiting", {
                    me: true,
                    at: APPROVED,
                  }),
                ],
                [person(ACADEMIC, "academic_supervisor", "to_approve")],
              ],
              me: supervisorMe({ state: "waiting", next_action: "wait" }),
              docs: [
                doc({
                  token: null,
                  mine: [slot("supervisor", { reason: "no_signature_file" })],
                }),
              ],
              route: route({ current_step: 3 }),
            }),
          ),
        ),
      ),
      entry("signing_done", "Готово, дальше другой подписант", () =>
        view(
          ready(
            academicTask("done", {
              steps: [
                [person(SR_AUTHOR.name, "author", "done", { at: SENT })],
                [
                  person(SR_SUPERVISOR.name, "supervisor", "to_sign", {
                    at: APPROVED,
                  }),
                ],
                [
                  person(ACADEMIC, "academic_supervisor", "done", {
                    me: true,
                    at: "2026-11-12T08:00:00Z",
                  }),
                ],
              ],
              me: {
                ...academicTask("done").me,
                state: "done",
                next_action: "done",
                image_ready: true,
                methods: [],
              },
              docs: [
                doc({
                  token: null,
                  frozen: true,
                  mine: [
                    slot("academic_supervisor", {
                      status: "signed",
                      reason: null,
                    }),
                  ],
                }),
              ],
            }),
          ),
        ),
      ),
      entry("signing_completed", "Все подписали", () =>
        view(
          ready(
            supervisorTurn({
              route: route({
                status: "completed",
                phase: "done",
                current_step: null,
              }),
              steps: [
                [person(SR_AUTHOR.name, "author", "done", { at: SENT })],
                [
                  person(SR_SUPERVISOR.name, "supervisor", "done", {
                    me: true,
                    at: APPROVED,
                  }),
                ],
              ],
              me: supervisorMe({
                state: "done",
                next_action: "done",
                methods: [],
              }),
              docs: [
                doc({
                  token: null,
                  frozen: true,
                  mine: [
                    slot("supervisor", { status: "signed", reason: null }),
                  ],
                }),
              ],
              events: [
                makeRouteEvent({ at: SENT }),
                makeRouteEvent({
                  id: "sre_02",
                  kind: "approved",
                  at: APPROVED,
                  who: SR_SUPERVISOR.name,
                }),
                makeRouteEvent({
                  id: "sre_03",
                  kind: "frozen",
                  at: APPROVED,
                  who: null,
                }),
                makeRouteEvent({
                  id: "sre_04",
                  kind: "signed",
                  at: APPROVED,
                  who: SR_SUPERVISOR.name,
                }),
                makeRouteEvent({
                  id: "sre_05",
                  kind: "completed",
                  at: APPROVED,
                  who: null,
                }),
              ],
            }),
          ),
        ),
      ),
    ],
  },
  {
    id: "signing-stopped",
    title: "Подписант: маршрут остановлен или закрыт",
    entries: [
      entry("signing_returned_mine", "Он вернул на доработку", () =>
        view(
          ready(
            supervisorTurn({
              route: route({
                status: "returned",
                phase: null,
                current_step: null,
                stop_reason: "returned",
              }),
              steps: [
                [person(SR_AUTHOR.name, "author", "waiting", { at: SENT })],
                [
                  person(SR_SUPERVISOR.name, "supervisor", "returned", {
                    me: true,
                  }),
                ],
                [person(ACADEMIC, "academic_supervisor", "waiting")],
              ],
              me: supervisorMe({ state: "returned", next_action: "wait" }),
              docs: [doc({ token: null })],
              events: [
                makeRouteEvent({ at: SENT }),
                makeRouteEvent({
                  id: "sre_02",
                  kind: "returned",
                  at: APPROVED,
                  who: SR_SUPERVISOR.name,
                  comment: RETURN_COMMENT,
                  reason: "returned",
                }),
              ],
            }),
          ),
        ),
      ),
      entry("signing_returned_other", "Вернул другой участник", () =>
        view(
          ready(
            academicTask("waiting", {
              steps: [
                [person(SR_AUTHOR.name, "author", "waiting", { at: SENT })],
                [person(SR_SUPERVISOR.name, "supervisor", "returned")],
                [
                  person(ACADEMIC, "academic_supervisor", "waiting", {
                    me: true,
                  }),
                ],
              ],
              route: route({
                status: "returned",
                phase: null,
                current_step: null,
                stop_reason: "returned",
              }),
              events: [
                makeRouteEvent({ at: SENT }),
                makeRouteEvent({
                  id: "sre_02",
                  kind: "returned",
                  at: APPROVED,
                  who: SR_SUPERVISOR.name,
                  comment: RETURN_COMMENT,
                  reason: "returned",
                }),
              ],
            }),
          ),
        ),
      ),
      entry("signing_paused_rebuilt", "Документ пересобран", () =>
        view(
          ready(
            supervisorTurn({
              route: route({
                status: "paused",
                phase: null,
                current_step: null,
                stop_reason: "rebuilt",
              }),
              me: supervisorMe({ state: "waiting", next_action: "wait" }),
              docs: [doc({ token: null })],
            }),
          ),
        ),
      ),
      entry("signing_paused_left", "Участник вышел из проекта", () =>
        view(
          ready(
            supervisorTurn({
              route: route({
                status: "paused",
                phase: null,
                current_step: null,
                stop_reason: "participant_left",
              }),
              me: supervisorMe({ state: "waiting", next_action: "wait" }),
              docs: [doc({ token: null })],
            }),
          ),
        ),
      ),
      entry("signing_cancelled", "Маршрут отменён", () =>
        view(
          ready(
            supervisorTurn({
              route: route({
                status: "cancelled",
                phase: null,
                current_step: null,
              }),
              me: supervisorMe({ state: "waiting", next_action: "wait" }),
              docs: [doc({ token: null })],
            }),
          ),
        ),
      ),
    ],
  },
  {
    id: "signing-page-states",
    title: "Подписант: загрузка и ошибки",
    entries: [
      entry("signing_not_found", "Не участник или ссылка устарела (404)", () =>
        view({ kind: "not_found" }),
      ),
      entry("signing_error", "Сервер не ответил", () =>
        view({ kind: "error" }),
      ),
      entry("signing_loading", "Загрузка", () => view({ kind: "loading" })),
    ],
  },
];
