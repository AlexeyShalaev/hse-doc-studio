import type { ReactNode } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { I18nextProvider } from "react-i18next";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { loadSigningNamespace } from "@shared/lib/i18n/signingNamespace";
import { installViewport } from "@shared/lib/viewport/testing";
import type { PdfStamp } from "@shared/ui";
import type { SigningTask, SigningTaskPerson } from "@entities/signing-route";
import {
  SIGNING_ROUTE_CONTRACT_EXAMPLES,
  SR_AUTHOR,
  SR_SUPERVISOR,
  makeRouteEvent,
  makeSigningTask,
} from "@entities/signing-route/testing";
import { formatMoment } from "../lib/format";

vi.mock("@shared/ui", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@shared/ui")),
  PdfViewer: ({
    url,
    stamps,
    jump,
  }: {
    url: string;
    stamps?: PdfStamp[];
    jump?: { page: number; token: number } | null;
  }) => (
    <div
      data-testid="pdf-viewer"
      data-url={url}
      data-frames={stamps?.filter((s) => s.highlight).length ?? 0}
      data-jump={jump ? `${String(jump.page)}#${String(jump.token)}` : ""}
    />
  ),
}));

import { SigningView, type SigningViewProps } from "./SigningView";

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
  card_name: null,
  changes_visible: false,
  ...extra,
});

const base = makeSigningTask();

/** Научрук в фазе согласования: «Согласовать», ключ плашки известен. */
const approveTask = (patch: Partial<SigningTask> = {}): SigningTask =>
  makeSigningTask({
    route: { ...base.route, phase: "approval" },
    steps: [
      [
        person(SR_AUTHOR.name, "author", "done", {
          at: "2026-11-10T09:00:00Z",
        }),
      ],
      [person(SR_SUPERVISOR.name, "supervisor", "to_approve", { me: true })],
      [person("Сидоров С.", "academic_supervisor", "waiting")],
    ],
    me: { ...base.me, state: "to_approve", next_action: "approve" },
    ...patch,
  });

const BEFORE_DEADLINE = Date.parse("2026-11-12T10:00:00Z");

const mount = (props: Partial<SigningViewProps> & { task?: SigningTask }) => {
  const { task = approveTask(), ...rest } = props;
  const onApprove = vi.fn();
  const onReturn = vi.fn(() => Promise.resolve(true));
  const ui = (node: ReactNode) => (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{node}</MemoryRouter>
    </I18nextProvider>
  );
  render(
    ui(
      <SigningView
        state={{ kind: "ready", task }}
        now={BEFORE_DEADLINE}
        onApprove={onApprove}
        onReturn={onReturn}
        pdfUrlOf={(doc) => `blob:${doc.doc_id}`}
        {...rest}
      />,
    ),
  );
  return { onApprove, onReturn };
};

beforeAll(async () => {
  await loadSigningNamespace();
});

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

describe("SigningView: его очередь", () => {
  it("шапка, ход маршрута, что нужно и «Согласовать»", async () => {
    const user = userEvent.setup();
    const { onApprove } = mount({});
    const head = screen.getByTestId("signing-head");
    expect(head).toHaveTextContent("Bertie: курсовой проект");
    expect(head).toHaveTextContent("Заявка на тему КП");
    expect(head).toHaveTextContent("Иванов И. И. просит подписать");
    expect(screen.getByTestId("signing-deadline")).toHaveAttribute(
      "data-overdue",
      "false",
    );
    expect(screen.getByTestId("signing-message")).toHaveTextContent(
      "Прошу подписать заявление до пятницы.",
    );
    const progress = screen.getByTestId("signing-progress");
    expect(progress).toHaveTextContent("Вы");
    expect(progress).toHaveTextContent("Сидоров С.");
    const status = screen.getByTestId("signing-status");
    expect(status).toHaveAttribute("data-kind", "turn");
    expect(status).toHaveTextContent("Ваша очередь: согласуйте документы");
    expect(status).toHaveTextContent("Согласовать 1 документ: открепленной ЭП");
    expect(screen.getByTestId("signing-method")).toHaveTextContent(
      "Ключ: Петров П. П., OpenPGP 1A2B 3C4D 5E6F 7A8B",
    );
    await user.click(screen.getByTestId("signing-approve"));
    expect(onApprove).toHaveBeenCalledOnce();
  });

  it("PDF с рамкой своего слота и переход к месту подписи", async () => {
    const user = userEvent.setup();
    mount({});
    const viewer = screen.getByTestId("pdf-viewer");
    expect(viewer).toHaveAttribute("data-url", "blob:topic_application");
    expect(viewer).toHaveAttribute("data-frames", "1");
    expect(viewer).toHaveAttribute("data-jump", "");
    await user.click(screen.getByTestId("signing-to-place"));
    expect(screen.getByTestId("pdf-viewer")).toHaveAttribute(
      "data-jump",
      "1#1",
    );
    expect(screen.getByTestId("signing-slot-supervisor")).toHaveTextContent(
      "стр. 1",
    );
  });

  it("картинкой без картинки: «Согласовать» ждёт", () => {
    mount({
      task: approveTask({
        me: {
          ...base.me,
          state: "to_approve",
          next_action: "approve",
          method: "image",
          image_ready: false,
          plate: null,
        },
      }),
    });
    expect(screen.getByTestId("signing-approve")).toBeDisabled();
    expect(screen.getByTestId("signing-approve-blocked")).toHaveTextContent(
      "Сначала добавьте картинку подписи.",
    );
    expect(screen.getByTestId("signing-method")).toHaveTextContent(
      "Нужна картинка подписи.",
    );
  });

  it("«Согласовать и подписать» без блока подписи: только возврат", () => {
    mount({ task: base });
    expect(screen.queryByTestId("signing-approve")).not.toBeInTheDocument();
    expect(screen.getByTestId("signing-return")).toBeEnabled();
    expect(screen.getByTestId("signing-status")).toHaveTextContent(
      "Ваша очередь: согласуйте и подпишите",
    );
  });

  it("расширение заменяет блок способа и главную кнопку", () => {
    const approve = vi.fn();
    mount({
      task: base,
      slot: (task) => ({
        projectId: task.route.project.id,
        routeId: task.route.id,
        task,
        busy: false,
        failure: null,
        expected: {},
        approve,
        sign: vi.fn(),
      }),
      extension: {
        method: (ctx) => (
          <div data-testid="w5-method">{ctx.task.me.next_action}</div>
        ),
        primary: (ctx) => (
          <button
            type="button"
            onClick={() => {
              void ctx.approve({
                sign: { identity_id: "k", passphrase: null },
              });
            }}
          >
            W5
          </button>
        ),
      },
    });
    expect(screen.getByTestId("w5-method")).toHaveTextContent(
      "approve_and_sign",
    );
    screen.getByRole("button", { name: "W5" }).click();
    expect(approve).toHaveBeenCalledWith({
      sign: { identity_id: "k", passphrase: null },
    });
  });

  it("срок прошёл и отказ действия видны", () => {
    mount({
      now: Date.parse("2026-11-16T09:00:00Z"),
      failure: "doc_changed",
    });
    expect(screen.getByTestId("signing-deadline")).toHaveAttribute(
      "data-overdue",
      "true",
    );
    expect(screen.getByTestId("signing-failure")).toHaveTextContent(
      "Документ изменился, пока страница была открыта",
    );
  });
});

describe("SigningView: общие отказы", () => {
  it.each([
    ["passphrase_invalid", "Пароль ключа не подошёл."],
    ["sign_failed", "Не удалось подписать. Проверьте ключ и пароль."],
  ] as const)("текст %s берётся из словаря ошибок Студии", (code, text) => {
    mount({ failure: code });
    expect(screen.getByTestId("signing-failure")).toHaveTextContent(text);
  });
});

describe("SigningView: вернуть на доработку", () => {
  it("комментарий обязателен, окно закрывается после ответа сервера", async () => {
    const user = userEvent.setup();
    const { onReturn } = mount({});
    await user.click(screen.getByTestId("signing-return"));
    const submit = await screen.findByTestId("signing-return-submit");
    expect(submit).toBeDisabled();
    await user.type(screen.getByTestId("signing-return-comment"), "   ");
    expect(submit).toBeDisabled();
    await user.type(
      screen.getByTestId("signing-return-comment"),
      "Уточните цель ",
    );
    await user.click(submit);
    expect(onReturn).toHaveBeenCalledWith("Уточните цель");
    await waitFor(() => {
      expect(
        screen.queryByTestId("signing-return-submit"),
      ).not.toBeInTheDocument();
    });
  });

  it("отказ сервера виден в окне, окно остаётся открытым", async () => {
    const user = userEvent.setup();
    mount({
      failure: "not_your_turn",
      onReturn: () => Promise.resolve(false),
    });
    await user.click(screen.getByTestId("signing-return"));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText("Сейчас не ваша очередь. Страница обновлена."),
    ).toBeTruthy();
    // Пока окно открыто, тот же отказ не дублируется на странице.
    expect(screen.queryByTestId("signing-failure")).not.toBeInTheDocument();
  });
});

describe("SigningView: другие состояния", () => {
  it("не участник: страница не найдена со ссылками на «Входящие» и главную", () => {
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <SigningView
            state={{ kind: "not_found" }}
            now={BEFORE_DEADLINE}
            onApprove={vi.fn()}
            onReturn={vi.fn()}
          />
        </MemoryRouter>
      </I18nextProvider>,
    );
    expect(screen.getByTestId("signing-page")).toHaveAttribute(
      "data-state",
      "not_found",
    );
    expect(screen.getByText("Страница подписи не найдена")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Входящие" })).toHaveAttribute(
      "href",
      "/inbox?tab=signing",
    );
  });

  it("ошибка загрузки: «Повторить»", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <SigningView
            state={{ kind: "error" }}
            now={BEFORE_DEADLINE}
            onApprove={vi.fn()}
            onReturn={vi.fn()}
            onRetry={onRetry}
          />
        </MemoryRouter>
      </I18nextProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("пока не его очередь: кто сейчас, без кнопок", () => {
    mount({
      task: approveTask({
        steps: [
          [
            person(SR_AUTHOR.name, "author", "done", {
              at: "2026-11-10T09:00:00Z",
            }),
          ],
          [person(SR_SUPERVISOR.name, "supervisor", "to_approve")],
          [
            person("Сидоров С.", "academic_supervisor", "waiting", {
              me: true,
            }),
          ],
        ],
        me: { ...base.me, state: "waiting", next_action: "wait" },
      }),
    });
    expect(screen.getByTestId("signing-status")).toHaveTextContent(
      "Сейчас ждём: Научный руководитель Петров П. П.",
    );
    expect(screen.queryByTestId("signing-actions")).not.toBeInTheDocument();
    expect(screen.queryByTestId("signing-method")).not.toBeInTheDocument();
  });

  it("автор согласовал раньше: когда попросят ЭП и кто не принял приглашение", () => {
    // Случай с сервера: автор с открепленной ЭП согласовал при отправке, руководители (картинки)
    // ещё не приняли приглашение. Их ссылки страница показывает под карточкой (`note`).
    mount({
      task: approveTask({
        steps: [
          [
            person(SR_AUTHOR.name, "author", "waiting", {
              me: true,
              at: "2026-11-10T09:00:00Z",
            }),
          ],
          [
            person("h***@hse.ru", "supervisor", "invited", {
              card_name: "Салех Х. М.",
              changes_visible: true,
            }),
          ],
          [
            person("s***@hse.ru", "academic_supervisor", "invited", {
              changes_visible: true,
            }),
          ],
        ],
        me: {
          ...base.me,
          state: "waiting",
          next_action: "wait",
          method: "detached",
        },
      }),
      note: <p data-testid="note">ссылки</p>,
    });
    const card = screen.getByTestId("signing-status");
    expect(card).toHaveAttribute("data-kind", "approved");
    expect(card).toHaveTextContent(
      "Вы уже согласовали. Электронную подпись Студия попросит поставить после фиксации PDF, когда согласуют: Научный руководитель Салех Х. М. (шаг 2 из 3, приглашение не принято), Академический руководитель s***@hse.ru (шаг 3 из 3, приглашение не принято).",
    );
    expect(card).toHaveTextContent(
      "Сейчас ждём: Научный руководитель Салех Х. М., приглашение не принято.",
    );
    expect(screen.getByTestId("note")).toBeInTheDocument();
  });

  it("возврат другим участником: кто и комментарий", () => {
    mount({
      task: approveTask({
        route: {
          ...base.route,
          status: "returned",
          phase: null,
          stop_reason: "returned",
        },
        me: { ...base.me, state: "waiting", next_action: "wait" },
        events: [
          makeRouteEvent(),
          makeRouteEvent({
            id: "sre_2",
            kind: "returned",
            who: "Сидоров С.",
            comment: "Уточните цель",
            reason: "returned",
          }),
        ],
      }),
    });
    const status = screen.getByTestId("signing-status");
    expect(status).toHaveAttribute("data-kind", "returned");
    expect(status).toHaveTextContent("Документы вернули на доработку");
    expect(status).toHaveTextContent("Сидоров С.: «Уточните цель»");
    expect(screen.getByTestId("signing-history")).toHaveTextContent(
      "Уточните цель",
    );
  });

  it.each([
    ["rebuilt", "Документ изменился после отправки"],
    ["participant_left", "Состав подписантов изменился"],
  ] as const)("остановка %s объясняет причину", (reason, text) => {
    mount({
      task: approveTask({
        route: {
          ...base.route,
          status: "paused",
          phase: null,
          stop_reason: reason,
        },
        me: { ...base.me, state: "waiting", next_action: "wait" },
      }),
    });
    expect(screen.getByTestId("signing-status")).toHaveTextContent(text);
  });

  it("все подписали", () => {
    mount({
      task: approveTask({
        route: { ...base.route, status: "completed", phase: "done" },
        me: { ...base.me, state: "done", next_action: "done" },
      }),
    });
    expect(screen.getByTestId("signing-status")).toHaveTextContent(
      "Все подписали",
    );
  });

  it("вкладки документов переключают PDF", async () => {
    const user = userEvent.setup();
    const [doc] = base.docs;
    if (!doc) throw new Error("fixture without docs");
    mount({
      task: approveTask({
        docs: [
          doc,
          {
            ...doc,
            doc_id: "approval_sheet",
            name: { ru: "Лист согласования", en: "Approval sheet" },
          },
        ],
      }),
    });
    expect(screen.getByTestId("signing-status")).toHaveTextContent(
      "Согласовать 2 документа",
    );
    await user.click(screen.getByTestId("signing-doc-tab-approval_sheet"));
    expect(screen.getByTestId("pdf-viewer")).toHaveAttribute(
      "data-url",
      "blob:approval_sheet",
    );
  });
});

describe("SigningView: телефон", () => {
  it("кнопки внизу экрана, а не в колонке", () => {
    const viewport = installViewport(390);
    try {
      mount({});
      const bar = document.querySelector(".sgn-actionbar");
      expect(bar).not.toBeNull();
      expect(
        within(bar as HTMLElement).getByTestId("signing-approve"),
      ).toBeTruthy();
      expect(document.querySelector(".sgn-side .sgn-actions")).toBeNull();
    } finally {
      viewport.restore();
    }
  });

  it("на английском", async () => {
    await i18n.changeLanguage("en");
    mount({});
    expect(screen.getByTestId("signing-status")).toHaveTextContent(
      "Your turn: approve the documents",
    );
    expect(screen.getByTestId("signing-approve")).toHaveTextContent("Approve");
  });
});

/** Эталон W7: заявление изменилось, отзыв без изменений (подпись научрука на нём осталась). */
const newVersion = SIGNING_ROUTE_CONTRACT_EXAMPLES.SigningTask
  ?.new_version as SigningTask;

/** Автор открыл свою страницу подписи, а рабочая сборка ушла от версии на подписи. */
const authorDiverged = (status: SigningTask["route"]["status"] = "active") =>
  makeSigningTask({
    route: { ...base.route, status },
    docs: base.docs.map((d) => ({ ...d, changed: true })),
  });

describe("SigningView: версия на подписи", () => {
  it("над документом дата версии, которую подписывают", () => {
    mount({});
    const version = screen.getByTestId("signing-doc-version");
    expect(version).toHaveAttribute("data-kind", "signing");
    expect(version).toHaveTextContent(
      `Вы подписываете версию от ${formatMoment("2026-11-10T09:00:00Z")}`,
    );
  });

  it("новая версия: что изменилось, сообщение автора и действие только по нему", async () => {
    const user = userEvent.setup();
    mount({ task: newVersion });
    const notice = screen.getByTestId("signing-new-version");
    expect(notice).toHaveTextContent(
      "Новая версия: изменился документ «Заявление о выборе темы». Согласуйте его заново.",
    );
    // Сообщение автора в плашке, в шапке не повторяется.
    expect(within(notice).getByTestId("signing-message")).toHaveTextContent(
      "Исправил формулировку темы.",
    );
    expect(screen.getAllByTestId("signing-message")).toHaveLength(1);
    // Строки «документ изменился после вашего согласования» нет: её заменяет плашка.
    const status = screen.getByTestId("signing-status");
    expect(status).not.toHaveTextContent("Документ изменился");
    expect(status).toHaveTextContent("Согласовать 1 документ");
    expect(screen.queryByTestId("signing-doc-kept")).toBeNull();

    await user.click(screen.getByTestId("signing-doc-tab-supervisor_review"));
    expect(screen.getByTestId("signing-doc-kept")).toHaveTextContent(
      "Без изменений: вы уже подписали",
    );
    expect(screen.getByTestId("signing-doc-version")).toHaveTextContent(
      `Версия на подписи от ${formatMoment("2026-11-10T09:00:00Z")}`,
    );
  });

  it("вне своей очереди плашка новой версии без призыва действовать", () => {
    mount({
      task: {
        ...newVersion,
        me: { ...newVersion.me, state: "waiting", next_action: "wait" },
        docs: newVersion.docs.map((d) => ({ ...d, token: null })),
      },
    });
    const notice = screen.getByTestId("signing-new-version");
    expect(notice).toHaveTextContent(
      "Новая версия: изменился документ «Заявление о выборе темы».",
    );
    expect(notice).not.toHaveTextContent("заново");
  });

  it("подписанту расхождение не показывается", () => {
    mount({ task: newVersion });
    expect(screen.queryByTestId("signing-divergence")).toBeNull();
  });

  it("автор видит расхождение и ссылку на карточку", () => {
    mount({ task: authorDiverged() });
    const banner = screen.getByTestId("signing-divergence");
    expect(banner).toHaveTextContent(
      `Есть изменения после отправки на подпись. Подписывают версию от ${formatMoment("2026-11-10T09:00:00Z")}.`,
    );
    expect(screen.getByTestId("signing-doc-version")).toHaveAttribute(
      "data-kind",
      "signing",
    );
    expect(
      within(banner).getByTestId("signing-send-new-version"),
    ).toHaveAttribute(
      "href",
      "/projects/p_01hxa1c4de/submit/cp/topic-approval",
    );
    expect(banner).toHaveTextContent("Отправить новую версию");
  });

  it("завершённый маршрут: все подписали прежнюю версию", () => {
    mount({ task: authorDiverged("completed") });
    expect(screen.getByTestId("signing-divergence")).toHaveTextContent(
      `Все подписали версию от ${formatMoment("2026-11-10T09:00:00Z")}. Есть изменения после подписания.`,
    );
    expect(screen.getByTestId("signing-doc-version")).toHaveTextContent(
      "Подписана версия от",
    );
  });

  it("на английском", async () => {
    await i18n.changeLanguage("en");
    mount({ task: newVersion });
    expect(screen.getByTestId("signing-new-version")).toHaveTextContent(
      "New version: the document “Topic selection application” has changed. Approve it again.",
    );
  });
});
