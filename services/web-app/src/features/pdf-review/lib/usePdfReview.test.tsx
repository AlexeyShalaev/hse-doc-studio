import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { PlacedThread, ReviewThread } from "@entities/review";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

const api = vi.hoisted(() => ({
  documentReview: vi.fn(),
  createPdfThread: vi.fn(),
  reply: vi.fn(),
  setStatus: vi.fn(),
  editComment: vi.fn(),
  deleteComment: vi.fn(),
  mentions: vi.fn(),
  threads: vi.fn(),
  createThread: vi.fn(),
}));
vi.mock("@entities/review/api/reviewApi", () => ({ reviewApi: api }));

import { usePdfReview, type PdfReviewViewer } from "./usePdfReview";

const base = {
  status: "open" as const,
  created_by: "u_rita",
  created_by_name: "Рита",
  created_at: "2026-11-13T09:00:00Z",
  updated_at: "2026-11-13T09:00:00Z",
  resolved_by_name: null,
  resolved_at: null,
};
const comment = (id: string, body: string) => ({
  id,
  author_id: "u_rita",
  author_name: "Рита",
  body,
  mentions: [],
  created_at: "2026-11-13T09:00:00Z",
  edited_at: null,
});
const textThread: ReviewThread = {
  ...base,
  id: "rvt_text",
  path: "chapters/intro.tex",
  anchor: {
    kind: "text",
    quote: "совместную правку",
    prefix: "",
    suffix: "",
    start: 0,
    end: 17,
  },
  comments: [comment("c1", "Уточните термин")],
};
const pdfThread: ReviewThread = {
  ...base,
  id: "rvt_pdf",
  path: "report/report.pdf",
  anchor: {
    kind: "pdf",
    doc_id: "report",
    page: 1,
    rects: [{ x: 72, y: 60, width: 200, height: 12 }],
    text: "ФАКУЛЬТЕТ КОМПЬЮТЕРНЫХ НАУК",
    build_sha: "old",
  },
  comments: [comment("c2", "Опечатка в шапке")],
};
const items: PlacedThread[] = [
  {
    thread: textThread,
    place: {
      page: 2,
      rects: [{ x: 72, y: 300, width: 450, height: 14 }],
      text: "совместную правку",
      exact: false,
    },
  },
  {
    thread: pdfThread,
    place: {
      page: 1,
      rects: [{ x: 72, y: 60, width: 200, height: 12 }],
      text: "ФАКУЛЬТЕТ КОМПЬЮТЕРНЫХ НАУК",
      exact: false,
    },
  },
];

let viewer: PdfReviewViewer | null = null;
const keep = (next: PdfReviewViewer): void => {
  viewer = next;
};
const Harness = ({ onViewer }: { onViewer: (v: PdfReviewViewer) => void }) => {
  const review = usePdfReview({
    projectId: "p1",
    docId: "report",
    enabled: true,
    canComment: true,
    canModerate: false,
    isOwner: false,
    currentUserId: "u_rita",
  });
  useEffect(() => {
    onViewer(review.viewer);
  });
  return (
    <>
      {review.toolbar}
      {review.panel}
    </>
  );
};

const mount = () =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter>
          <Harness onViewer={keep} />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  // jsdom не прокручивает: карточка выбранного треда зовёт scrollIntoView.
  Element.prototype.scrollIntoView = vi.fn();
  api.documentReview.mockResolvedValue({ build_sha: "new", items });
  api.mentions.mockResolvedValue([]);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  viewer = null;
});

describe("usePdfReview", () => {
  it("ставит метки: исходниковый тред может встать по строке SyncTeX, PDF-тред только по тексту", async () => {
    mount();

    await waitFor(() => {
      expect(viewer?.marks).toHaveLength(2);
    });
    const byId = Object.fromEntries(
      (viewer?.marks ?? []).map((m) => [m.id, m]),
    );
    expect(byId.rvt_text?.fallback).toBe(true);
    expect(byId.rvt_pdf?.fallback).toBe(false);
    expect(byId.rvt_pdf?.title).toBe("Комментарий: Рита");
    expect(screen.getByTestId("pdf-review-toggle").textContent).toContain("2");
  });

  it("PDF пересобран и место не нашлось: в списке пометка «Место изменилось»", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => {
      expect(viewer?.marks).toHaveLength(2);
    });

    act(() => {
      viewer?.onMarksPlaced({ rvt_text: true, rvt_pdf: false });
    });
    await user.click(screen.getByTestId("pdf-review-toggle"));

    const card = within(screen.getByTestId("review-thread-rvt_pdf"));
    expect(card.getByTestId("review-anchor-state").textContent).toBe(
      "Место изменилось: PDF пересобран",
    );
    expect(card.getByText("К месту в PDF, стр. 1")).toBeTruthy();
    const text = within(screen.getByTestId("review-thread-rvt_text"));
    expect(text.queryByTestId("review-anchor-state")).toBeNull();
    expect(text.getByText("Исходник: chapters/intro.tex")).toBeTruthy();
  });

  it("«Комментировать» на выделении открывает новый тред и отправляет выделение на сервер", async () => {
    const user = userEvent.setup();
    api.createPdfThread.mockResolvedValue(textThread);
    mount();
    await waitFor(() => {
      expect(viewer?.onComment).toBeDefined();
    });

    act(() => {
      viewer?.onComment?.({
        text: "совместную правку",
        page: 2,
        rects: [{ x: 72, y: 300, width: 120, height: 14 }],
      });
    });
    const form = within(await screen.findByTestId("review-new-thread"));
    await user.type(form.getByTestId("review-composer"), "Поясните");
    await user.click(form.getByTestId("review-composer-submit"));

    await waitFor(() => {
      expect(api.createPdfThread).toHaveBeenCalledWith("p1", {
        doc_id: "report",
        page: 2,
        rects: [{ x: 72, y: 300, width: 120, height: 14 }],
        text: "совместную правку",
        body: "Поясните",
        mentions: [],
      });
    });
  });
});
