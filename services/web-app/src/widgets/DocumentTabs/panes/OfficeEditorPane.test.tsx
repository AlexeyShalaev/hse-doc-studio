import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import {
  SR_DOC,
  SR_PROJECT_ID,
  makeSigningRouteSummary,
} from "@entities/signing-route/testing";
import { makeGuardHarness } from "@entities/signing-route/testing/guard";
import { OfficeEditorPane } from "./OfficeEditorPane";

// The `@shared/ui` barrel eagerly loads pdfjs-dist, which needs DOMMatrix.
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

// Сохранение ONLYOFFICE уходит на сервер мимо страницы: вопрос задаётся до открытия редактора.

const renderPane = (docId: string) => {
  const get = vi.spyOn(apiClient, "get").mockResolvedValue({
    data: { state: "unavailable", detail: "Редактор выключен" },
  });
  const harness = makeGuardHarness({
    routes: [makeSigningRouteSummary({ docs: [SR_DOC.doc_id] })],
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter>{harness.wrapper({ children })}</MemoryRouter>
  );
  render(<OfficeEditorPane projectId={SR_PROJECT_ID} docId={docId} />, {
    wrapper: Wrapper,
  });
  const sessionCalls = () =>
    get.mock.calls.filter(([url]) => url.endsWith("/office-editor"));
  return { sessionCalls };
};

describe("OfficeEditorPane and the signing guard", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("asks before opening the editor of a document out for signing", async () => {
    const user = userEvent.setup();
    const { sessionCalls } = renderPane(SR_DOC.doc_id);

    expect(
      await screen.findByRole("dialog", { name: "Документ на подписании" }),
    ).toBeInTheDocument();
    expect(sessionCalls()).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    await waitFor(() => {
      expect(sessionCalls()).toHaveLength(1);
    });
    expect(await screen.findByText("Редактор выключен")).toBeInTheDocument();
  });

  it("cancel keeps the editor closed and offers to open it again", async () => {
    const user = userEvent.setup();
    const { sessionCalls } = renderPane(SR_DOC.doc_id);

    await user.click(await screen.findByRole("button", { name: "Отмена" }));
    expect(screen.getByText("Редактор не открыт")).toBeInTheDocument();
    expect(sessionCalls()).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Открыть редактор" }));
    await user.click(
      await screen.findByRole("button", { name: "Продолжить" }),
    );
    await waitFor(() => {
      expect(sessionCalls()).toHaveLength(1);
    });
  });

  it("opens at once for a document no route holds", async () => {
    const { sessionCalls } = renderPane("presentation");
    await waitFor(() => {
      expect(sessionCalls()).toHaveLength(1);
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
