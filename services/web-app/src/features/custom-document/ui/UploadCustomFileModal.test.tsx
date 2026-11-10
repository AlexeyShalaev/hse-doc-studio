import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import {
  SR_DOC,
  SR_PROJECT_ID,
  makeSigningRouteSummary,
} from "@entities/signing-route/testing";
import { makeGuardHarness } from "@entities/signing-route/testing/guard";

// The `@shared/ui` barrel eagerly loads pdfjs-dist, which needs DOMMatrix.
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

const upload = vi.fn<(file: File) => Promise<void>>();

vi.mock("@entities/document", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@entities/document")>()),
  useCustomFileActions: () => ({
    upload,
    remove: vi.fn(),
    isUploading: false,
    isRemoving: false,
  }),
}));

import { UploadCustomFileModal } from "./UploadCustomFileModal";

const renderModal = (docId: string) => {
  const onClose = vi.fn();
  const harness = makeGuardHarness({
    routes: [makeSigningRouteSummary({ docs: [SR_DOC.doc_id] })],
  });
  render(
    <UploadCustomFileModal
      isOpen
      onClose={onClose}
      projectId={SR_PROJECT_ID}
      docId={docId}
      docName={SR_DOC.name.ru}
    />,
    { wrapper: harness.wrapper },
  );
  return { onClose };
};

const pickAndUpload = async (user: ReturnType<typeof userEvent.setup>) => {
  const input = document.body.querySelector<HTMLInputElement>(
    'input[type="file"]',
  );
  if (!input) throw new Error("no file input");
  await user.upload(input, new File(["%PDF"], "signed.pdf"));
  await user.click(screen.getByRole("button", { name: "Загрузить" }));
};

describe("UploadCustomFileModal and the signing guard", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    upload.mockReset().mockResolvedValue(undefined);
  });
  afterEach(cleanup);

  it("asks before replacing the file of a document out for signing", async () => {
    const user = userEvent.setup();
    const { onClose } = renderModal(SR_DOC.doc_id);
    await pickAndUpload(user);

    expect(
      await screen.findByRole("dialog", { name: "Документ на подписании" }),
    ).toBeInTheDocument();
    expect(upload).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    await waitFor(() => {
      expect(upload).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("cancel uploads nothing and keeps the upload window", async () => {
    const user = userEvent.setup();
    const { onClose } = renderModal(SR_DOC.doc_id);
    await pickAndUpload(user);
    await user.click(await screen.findByRole("button", { name: "Отмена" }));
    expect(upload).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(
      screen.getByRole("dialog", { name: "Загрузить свой файл" }),
    ).toBeInTheDocument();
  });

  it("uploads at once for a document no route holds", async () => {
    const user = userEvent.setup();
    renderModal("presentation");
    await pickAndUpload(user);
    expect(upload).toHaveBeenCalledTimes(1);
  });
});
