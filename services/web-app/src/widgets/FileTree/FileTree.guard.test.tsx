import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import { fileKeys } from "@entities/document";
import {
  SR_DOC,
  SR_PROJECT_ID,
  makeSigningRouteSummary,
} from "@entities/signing-route/testing";
import { makeGuardHarness } from "@entities/signing-route/testing/guard";
import { FileTree } from "./FileTree";

// The `@shared/ui` barrel eagerly loads pdfjs-dist, which needs DOMMatrix.
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

const AT = "2026-11-10T09:00:00Z";
const file = (path: string) => ({
  path,
  size: 10,
  modified_at: AT,
  deletable: true,
  is_dir: false,
});

const renderTree = () => {
  const del = vi.spyOn(apiClient, "delete").mockResolvedValue({ data: null });
  vi.spyOn(apiClient, "get").mockImplementation(() => new Promise(() => {}));
  const harness = makeGuardHarness({
    routes: [makeSigningRouteSummary({ docs: [SR_DOC.doc_id] })],
  });
  harness.client.setQueryData(fileKeys.tree(SR_PROJECT_ID), [
    file(`${SR_DOC.doc_id}/intro.tex`),
    file("supervisor_review/review.tex"),
    file("common/refs.bib"),
  ]);
  render(
    <FileTree
      projectId={SR_PROJECT_ID}
      selectedPath={undefined}
      onSelect={vi.fn()}
    />,
    { wrapper: harness.wrapper },
  );
  return { del };
};

/** Правый клик по файлу, «Удалить» в меню и подтверждение удаления. */
const deleteFile = async (
  user: ReturnType<typeof userEvent.setup>,
  name: string,
) => {
  fireEvent.contextMenu(screen.getByText(name));
  await user.click(screen.getByRole("button", { name: "Удалить" }));
  const confirm = await screen.findByRole("dialog", { name: "Удалить файл?" });
  await user.click(within(confirm).getByRole("button", { name: "Удалить" }));
};

describe("FileTree and the signing guard", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("asks before deleting a file of a document out for signing", async () => {
    const user = userEvent.setup();
    const { del } = renderTree();
    await deleteFile(user, "intro.tex");

    expect(
      await screen.findByRole("dialog", { name: "Документ на подписании" }),
    ).toBeInTheDocument();
    expect(del).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    await waitFor(() => {
      expect(del).toHaveBeenCalledWith(
        `/projects/${SR_PROJECT_ID}/files/${SR_DOC.doc_id}/intro.tex`,
      );
    });
  });

  it("asks with the list of documents before deleting a shared file, cancel keeps it", async () => {
    const user = userEvent.setup();
    const { del } = renderTree();
    await deleteFile(user, "refs.bib");

    expect(
      await screen.findByRole("dialog", { name: "Документ на подписании" }),
    ).toHaveTextContent("Документ на подписании: Заявление о выборе темы.");
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(del).not.toHaveBeenCalled();
  });

  it("deletes at once in a document no route holds", async () => {
    const user = userEvent.setup();
    const { del } = renderTree();
    await deleteFile(user, "review.tex");
    await waitFor(() => {
      expect(del).toHaveBeenCalledTimes(1);
    });
  });
});
