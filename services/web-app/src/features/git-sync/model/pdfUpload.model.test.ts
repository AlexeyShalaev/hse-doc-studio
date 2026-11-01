import { describe, expect, it } from "vitest";
import { connected, noRemote } from "../testing/statusFactory";
import { pdfUploadStatus } from "./pdfUpload.model";

describe("pdfUploadStatus", () => {
  it("is null for projects that are not from a Studio server or have uploads off", () => {
    expect(pdfUploadStatus(undefined)).toBeNull();
    expect(pdfUploadStatus(noRemote())).toBeNull();
    expect(
      pdfUploadStatus(
        connected({
          pdf_upload: { enabled: false, available: true, last: null },
        }),
      ),
    ).toBeNull();
  });

  it("carries the last upload for a Studio server project", () => {
    const status = connected({
      pdf_upload: {
        enabled: true,
        available: true,
        last: {
          doc_id: "cw",
          at: "2026-11-02T10:00:00Z",
          ok: false,
          error: "pdf_forbidden",
        },
      },
    });

    expect(pdfUploadStatus(status)).toEqual({
      last: {
        docId: "cw",
        at: "2026-11-02T10:00:00Z",
        ok: false,
        error: "pdf_forbidden",
        message: null,
      },
    });
  });
});
