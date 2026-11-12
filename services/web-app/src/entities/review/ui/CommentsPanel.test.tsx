import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { Anchor, ReviewThread } from "../model/review.schema";

// Панель тянет за собой barrel @shared/ui с pdfjs-dist, которому в jsdom нужен DOMMatrix.
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

const api = vi.hoisted(() => ({
  createThread: vi.fn(),
  reply: vi.fn(),
  setStatus: vi.fn(),
  editComment: vi.fn(),
  deleteComment: vi.fn(),
  mentions: vi.fn(),
  threads: vi.fn(),
}));
vi.mock("../api/reviewApi", () => ({ reviewApi: api }));

import {
  CommentsPanel,
  type CommentsPanelProps,
  type PendingThread,
} from "./CommentsPanel";

const anchor: Anchor = {
  kind: "text",
  quote: "совместную правку",
  prefix: "изучаем ",
  suffix: " текста",
  start: 20,
  end: 37,
};
const comment = (
  id: string,
  author: string,
  body: string,
  authorId: string,
) => ({
  id,
  author_id: authorId,
  author_name: author,
  body,
  mentions: [],
  created_at: "2026-11-03T09:00:00Z",
  edited_at: null,
});
const thread = (over: Partial<ReviewThread> = {}): ReviewThread => ({
  id: "rvt_1",
  path: "main.tex",
  anchor,
  status: "open",
  created_by: "u_rita",
  created_by_name: "Рита",
  created_at: "2026-11-03T09:00:00Z",
  updated_at: "2026-11-03T09:00:00Z",
  resolved_by_name: null,
  resolved_at: null,
  comments: [comment("rvc_1", "Рита", "Уточните термин", "u_rita")],
  ...over,
});

const baseProps = (
  over: Partial<CommentsPanelProps> = {},
): CommentsPanelProps => ({
  projectId: "p1",
  threads: [thread()],
  activeId: null,
  onActivate: vi.fn(),
  pending: null,
  onPendingDone: vi.fn(),
  showResolved: false,
  onToggleResolved: vi.fn(),
  canComment: true,
  canModerate: false,
  isOwner: false,
  currentUserId: "u_rita",
  onClose: vi.fn(),
  ...over,
});

const pendingFor = (): PendingThread => ({
  quote: anchor.quote,
  create: (body, mentions) =>
    api.createThread("p1", {
      path: "main.tex",
      anchor,
      body,
      mentions,
    }) as Promise<ReviewThread>,
});

const mount = (props: CommentsPanelProps) =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter>
          <CommentsPanel {...props} />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  api.threads.mockResolvedValue([]);
  api.mentions.mockResolvedValue([
    { user_id: "u_boris", name: "Борис", detail: null },
  ]);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CommentsPanel", () => {
  it("shows open threads and hides resolved ones until the filter is switched", () => {
    const resolved = thread({
      id: "rvt_2",
      status: "resolved",
      resolved_by_name: "Анна",
    });
    mount(baseProps({ threads: [thread(), resolved] }));

    expect(screen.getByTestId("review-thread-rvt_1")).toBeTruthy();
    expect(screen.queryByTestId("review-thread-rvt_2")).toBeNull();
    cleanup();
    mount(baseProps({ threads: [thread(), resolved], showResolved: true }));
    expect(screen.getByTestId("review-thread-rvt_2").textContent).toContain(
      "Решено: Анна",
    );
  });

  it("explains a thread whose fragment was moved or lost", () => {
    mount(baseProps({ stateOf: () => "Место изменилось: PDF пересобран" }));

    expect(screen.getByTestId("review-anchor-state").textContent).toContain(
      "Место изменилось",
    );
  });

  it("replies with the mentioned people picked from suggestions", async () => {
    const user = userEvent.setup();
    api.reply.mockResolvedValue(thread());
    mount(baseProps());
    const card = within(screen.getByTestId("review-thread-rvt_1"));

    await user.type(card.getByTestId("review-composer"), "Посмотри @Бо");
    await user.click(await screen.findByText("Борис"));
    await user.click(card.getByTestId("review-composer-submit"));

    await waitFor(() => {
      expect(api.reply).toHaveBeenCalledWith("p1", "rvt_1", "Посмотри @Борис", [
        "u_boris",
      ]);
    });
  });

  it("lets the author resolve their own thread and reopen it", async () => {
    const user = userEvent.setup();
    api.setStatus.mockResolvedValue(thread({ status: "resolved" }));
    mount(baseProps());

    await user.click(screen.getByTestId("review-toggle-rvt_1"));

    await waitFor(() => {
      expect(api.setStatus).toHaveBeenCalledWith("p1", "rvt_1", "resolved");
    });
  });

  it("does not offer resolving somebody else's thread without edit rights", () => {
    mount(baseProps({ currentUserId: "u_other" }));

    expect(screen.queryByTestId("review-toggle-rvt_1")).toBeNull();
  });

  it("a reader sees threads but no composer", () => {
    mount(baseProps({ canComment: false }));

    expect(screen.queryByTestId("review-composer")).toBeNull();
    expect(screen.getByText(/писать — с ролью рецензента/)).toBeTruthy();
  });

  it("creates a thread for the pending selection and activates it", async () => {
    const user = userEvent.setup();
    api.createThread.mockResolvedValue(thread({ id: "rvt_new" }));
    const onCreated = vi.fn();
    const props = baseProps({ pending: pendingFor(), threads: [], onCreated });
    mount(props);

    await user.type(
      within(screen.getByTestId("review-new-thread")).getByTestId(
        "review-composer",
      ),
      "Новое замечание",
    );
    await user.click(
      within(screen.getByTestId("review-new-thread")).getByTestId(
        "review-composer-submit",
      ),
    );

    await waitFor(() => {
      expect(api.createThread).toHaveBeenCalledWith("p1", {
        path: "main.tex",
        anchor,
        body: "Новое замечание",
        mentions: [],
      });
    });
    await waitFor(() => {
      expect(props.onActivate).toHaveBeenCalledWith("rvt_new");
    });
    expect(props.onPendingDone).toHaveBeenCalled();
    expect(onCreated).toHaveBeenCalledWith(
      expect.objectContaining({ id: "rvt_new" }),
    );
  });

  it("shows the server's reason when the fragment is stale", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@shared/api");
    api.createThread.mockRejectedValue(
      new ApiError("stale", "anchor_stale", 409),
    );
    mount(baseProps({ pending: pendingFor(), threads: [] }));

    await user.type(screen.getByTestId("review-composer"), "x");
    await user.click(screen.getByTestId("review-composer-submit"));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Фрагмент уже изменили",
    );
  });
});

describe("CommentsPanel на телефоне", () => {
  it("opens as a bottom sheet across the screen", () => {
    mount(baseProps({ sheet: true }));

    const panel = screen.getByTestId("review-panel");
    expect(panel.dataset.layout).toBe("sheet");
    expect(panel.style.position).toBe("fixed");
  });

  it("shows extra details under the quote of each thread", () => {
    mount(baseProps({ details: (x) => <span>Файл {x.path}</span> }));

    expect(screen.getByText("Файл main.tex")).toBeTruthy();
  });
});
