import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { signingRouteKeys } from "../api/signingRouteQueries";
import type { GuardMemory, GuardTarget } from "../lib/editGuard";
import {
  SR_DOC,
  SR_PROJECT_ID,
  SR_REVIEW_DOC,
  makeSigningRouteSummary,
} from "../testing/fixtures";
import { freshGuardMemory, makeGuardHarness } from "../testing/guard";
import { useRouteEditGuard } from "./routeEditGuardContext";

const TOPIC = SR_DOC.doc_id;
const REVIEW = SR_REVIEW_DOC.doc_id;

/** Место правки: кнопка выполняет действие через предупреждение. */
const Editor = ({
  target,
  action,
  projectId = SR_PROJECT_ID,
}: {
  target: GuardTarget;
  action: () => void;
  projectId?: string;
}) => {
  const guard = useRouteEditGuard(projectId);
  const [names, setNames] = useState<string[]>([]);
  return (
    <>
      <button
        type="button"
        onClick={() => {
          guard.run(target, action);
        }}
      >
        edit
      </button>
      <button
        type="button"
        onClick={() => {
          setNames(guard.heldNames(target));
        }}
      >
        names
      </button>
      <output>{names.join("|")}</output>
    </>
  );
};

const dialog = () => screen.queryByRole("dialog");

const renderEditor = ({
  target,
  routes = [makeSigningRouteSummary({ docs: [TOPIC, REVIEW] })],
  memory = freshGuardMemory(),
}: {
  target: GuardTarget;
  routes?: ReturnType<typeof makeSigningRouteSummary>[];
  memory?: GuardMemory;
}) => {
  const action = vi.fn();
  const harness = makeGuardHarness({ routes, memory });
  const view = render(<Editor target={target} action={action} />, {
    wrapper: harness.wrapper,
  });
  return { action, harness, view };
};

describe("RouteEditGuardProvider", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("asks before the first change of a document out for signing, once per session", async () => {
    const user = userEvent.setup();
    const { action } = renderEditor({ target: { docIds: [TOPIC] } });

    await user.click(screen.getByRole("button", { name: "edit" }));
    const modal = await screen.findByRole("dialog", {
      name: "Документ на подписании",
    });
    expect(modal).toHaveTextContent(
      "Изменения не попадут в подписываемую версию. Продолжить?",
    );
    expect(modal).toHaveTextContent(
      "Чтобы подписали новую версию, после правки нажмите «Отправить новую версию» в карточке «Подписание».",
    );
    expect(action).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(action).toHaveBeenCalledTimes(1);
    expect(dialog()).toBeNull();

    // Второе изменение того же документа в том же раунде: без вопроса и сразу.
    await user.click(screen.getByRole("button", { name: "edit" }));
    expect(action).toHaveBeenCalledTimes(2);
    expect(dialog()).toBeNull();
  });

  it("does nothing on cancel and asks again next time", async () => {
    const user = userEvent.setup();
    const { action } = renderEditor({ target: { docIds: [TOPIC] } });

    await user.click(screen.getByRole("button", { name: "edit" }));
    await user.click(await screen.findByRole("button", { name: "Отмена" }));
    expect(action).not.toHaveBeenCalled();
    expect(dialog()).toBeNull();

    await user.click(screen.getByRole("button", { name: "edit" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("is keyboard friendly: Escape cancels, Tab and Enter continue", async () => {
    const user = userEvent.setup();
    const { action } = renderEditor({ target: { docIds: [TOPIC] } });

    await user.click(screen.getByRole("button", { name: "edit" }));
    await screen.findByRole("dialog");
    // Фокус внутри окна сразу, на безопасной кнопке.
    expect(screen.getByRole("button", { name: "Отмена" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(dialog()).toBeNull();
    expect(action).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "edit" }));
    await screen.findByRole("dialog");
    await user.tab();
    expect(screen.getByRole("button", { name: "Продолжить" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(action).toHaveBeenCalledTimes(1);
  });

  it("does not ask for a document no active route holds", async () => {
    const user = userEvent.setup();
    const { action } = renderEditor({
      target: { docIds: [TOPIC] },
      routes: [
        makeSigningRouteSummary({ status: "paused", docs: [TOPIC] }),
        makeSigningRouteSummary({
          id: "other",
          status: "completed",
          docs: [TOPIC],
        }),
        makeSigningRouteSummary({ id: "third", docs: [REVIEW] }),
      ],
    });
    await user.click(screen.getByRole("button", { name: "edit" }));
    expect(action).toHaveBeenCalledTimes(1);
    expect(dialog()).toBeNull();
  });

  it("asks again in a new round of the same route", async () => {
    const user = userEvent.setup();
    const { action, harness } = renderEditor({ target: { docIds: [TOPIC] } });
    await user.click(screen.getByRole("button", { name: "edit" }));
    await user.click(await screen.findByRole("button", { name: "Продолжить" }));
    expect(action).toHaveBeenCalledTimes(1);

    act(() => {
      harness.client.setQueryData(
        signingRouteKeys.list(SR_PROJECT_ID, null),
        { items: [makeSigningRouteSummary({ round: 2, docs: [TOPIC] })] },
      );
    });
    await user.click(screen.getByRole("button", { name: "edit" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(action).toHaveBeenCalledTimes(1);
  });

  it("lists the documents for shared files and project fields", async () => {
    const user = userEvent.setup();
    const { action } = renderEditor({ target: { paths: ["common/refs.bib"] } });
    await user.click(screen.getByRole("button", { name: "edit" }));
    const modal = await screen.findByRole("dialog", {
      name: "Документы на подписании",
    });
    expect(modal).toHaveTextContent(
      "Документы на подписании: Заявление о выборе темы, Отзыв руководителя. Изменения не попадут в подписываемые версии. Продолжить?",
    );
    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(action).toHaveBeenCalledTimes(1);
  });

  it("asks a project change once: every listed document is answered", async () => {
    const user = userEvent.setup();
    const memory = freshGuardMemory();
    const first = renderEditor({ target: { project: true }, memory });
    await user.click(screen.getByRole("button", { name: "edit" }));
    await user.click(await screen.findByRole("button", { name: "Продолжить" }));
    first.view.unmount();

    // Тот же сеанс: правка файла одного из перечисленных документов уже не спрашивает.
    const second = renderEditor({ target: { paths: ["supervisor_review/a.tex"] }, memory });
    await user.click(screen.getByRole("button", { name: "edit" }));
    expect(second.action).toHaveBeenCalledTimes(1);
    expect(dialog()).toBeNull();
  });

  it("lists only the documents still without an answer", async () => {
    const user = userEvent.setup();
    const memory = freshGuardMemory();
    const first = renderEditor({ target: { docIds: [TOPIC] }, memory });
    await user.click(screen.getByRole("button", { name: "edit" }));
    await user.click(await screen.findByRole("button", { name: "Продолжить" }));
    first.view.unmount();

    renderEditor({ target: { project: true }, memory });
    await user.click(screen.getByRole("button", { name: "edit" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent(
      "Документ на подписании: Отзыв руководителя. Изменения не попадут в подписываемую версию. Продолжить?",
    );
  });

  it("shows one window when two places ask about the same document", async () => {
    const user = userEvent.setup();
    const memory = freshGuardMemory();
    const harness = makeGuardHarness({
      routes: [makeSigningRouteSummary({ docs: [TOPIC] })],
      memory,
    });
    const answers: boolean[] = [];
    const Twice = () => {
      const guard = useRouteEditGuard(SR_PROJECT_ID);
      return (
        <button
          type="button"
          onClick={() => {
            void guard.confirm({ docIds: [TOPIC] }).then((ok) => answers.push(ok));
            void guard
              .confirm({ paths: [`${TOPIC}/x.tex`] })
              .then((ok) => answers.push(ok));
          }}
        >
          twice
        </button>
      );
    };
    render(<Twice />, { wrapper: harness.wrapper });
    await user.click(screen.getByRole("button", { name: "twice" }));
    await user.click(await screen.findByRole("button", { name: "Продолжить" }));
    expect(dialog()).toBeNull();
    expect(answers).toEqual([true, true]);
  });

  it("names the documents for the template update line", async () => {
    const user = userEvent.setup();
    renderEditor({ target: { paths: ["topic_application/a.tex", "README.md"] } });
    await user.click(screen.getByRole("button", { name: "names" }));
    expect(screen.getByRole("status")).toHaveTextContent(
      "Заявление о выборе темы|Отзыв руководителя",
    );
  });

  it("speaks English", async () => {
    await i18n.changeLanguage("en");
    const user = userEvent.setup();
    renderEditor({ target: { project: true } });
    await user.click(screen.getByRole("button", { name: "edit" }));
    const modal = await screen.findByRole("dialog", {
      name: "Documents out for signing",
    });
    expect(modal).toHaveTextContent(
      "Out for signing: Заявление о выборе темы, Отзыв руководителя. Changes will not reach the versions being signed. Continue?",
    );
    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument();
  });

  it("runs at once outside the provider of the project", async () => {
    const user = userEvent.setup();
    const action = vi.fn();
    const harness = makeGuardHarness({
      routes: [makeSigningRouteSummary({ docs: [TOPIC] })],
    });
    render(
      <Editor target={{ docIds: [TOPIC] }} action={action} projectId="other" />,
      { wrapper: harness.wrapper },
    );
    await user.click(screen.getByRole("button", { name: "edit" }));
    expect(action).toHaveBeenCalledTimes(1);
    expect(dialog()).toBeNull();

    cleanup();
    const bare = vi.fn();
    render(<Editor target={{ docIds: [TOPIC] }} action={bare} />);
    await user.click(screen.getByRole("button", { name: "edit" }));
    expect(bare).toHaveBeenCalledTimes(1);
  });
});
