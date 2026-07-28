import { useState } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { Info, ShieldOff } from "lucide-react";
import { useStartCompile } from "@entities/compile";
import {
  getCustomFileSignability,
  getDocMeta,
  useCompile,
  useDocument,
} from "@entities/document";
import { useProject } from "@entities/project";
import {
  useSignaturesState,
  useUpdateSignaturePlacement,
} from "@entities/signature";
import { useVersionDetail } from "@entities/template-catalog";
import { DocPlacementPanel, PdfStampEditor } from "@features/signature-stamper";
import type { UpdatePlacementRequest } from "@shared/api/types";
import { Spinner } from "@shared/ui/Spinner";

export type DocSignaturesPaneProps = {
  projectId: string;
  docId: string;
};

const personNameForSlot = (
  slotId: string,
  project: ReturnType<typeof useProject>["data"],
  owner: string | null,
): string | null => {
  if (!project) return null;
  // Team runtime slots carry the owner's slug — the signer is that author.
  if (owner != null) {
    return project.authors?.find((a) => a.slug === owner)?.name ?? null;
  }
  if (slotId === "author") return project.authors?.[0]?.name ?? null;
  if (slotId === "supervisor") return project.supervisor?.name ?? null;
  if (slotId === "co_supervisor") return project.co_supervisor?.name ?? null;
  return null;
};

export const DocSignaturesPane = ({
  projectId,
  docId,
}: DocSignaturesPaneProps) => {
  const { t } = useTranslation("documents");
  const navigate = useNavigate();
  const { data: project } = useProject(projectId);
  const { data: doc } = useDocument(projectId, docId);
  const { data: versionDetail, isLoading: vdLoading } = useVersionDetail(
    project?.lock.pack_id ?? "",
    project?.lock.template_id ?? "",
    project?.lock.version ?? "",
  );
  const { data: state, isLoading: stateLoading } =
    useSignaturesState(projectId);
  const { mutate: updatePlacement } = useUpdateSignaturePlacement();
  const { start, isRunning, slot } = useStartCompile(projectId, docId);

  // The signature preview needs a PDF, which exists iff the most recent build
  // actually produced one. Gate on the *compile* result, not doc.status: a doc
  // can be DocumentStatus.err (e.g. a GOST *content* check failed) while still
  // having a perfectly good PDF on disk — that PDF is signable.
  const lastCompileId = doc?.last_compile_id ?? "";
  const { data: lastCompile, isLoading: compileLoading } = useCompile(
    projectId,
    docId,
    lastCompileId,
  );

  // Shared page state between the placement sidebar and the PDF preview.
  // Lifting it here lets the sidebar's "Переместить сюда" button refer to
  // whatever page the user is currently viewing, and lets "Перейти" jump
  // the preview to the page where the slot already lives.
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);

  if (vdLoading || stateLoading || compileLoading || !state || !project) {
    return (
      <div
        className="flex items-center justify-center"
        style={{ padding: 32, flex: 1, minHeight: 0 }}
      >
        <Spinner size="sm" />
      </div>
    );
  }

  const signability = getCustomFileSignability(doc);

  // A custom document that's neither PDF nor convertible has no automatable
  // signing surface — advisory, not an error: the student is expected to sign
  // it themselves outside the app.
  if (signability === "unsignable") {
    return (
      <div
        className="flex flex-col items-center justify-center"
        style={{ flex: 1, padding: 40, gap: 16, minHeight: 0 }}
      >
        <div
          className="stripes flex items-center justify-center"
          style={{
            width: 220,
            height: 280,
            borderRadius: 6,
            border: "1px solid var(--border-strong)",
            color: "var(--fg-3)",
          }}
        >
          <div className="flex flex-col items-center" style={{ gap: 6 }}>
            <ShieldOff size={28} />
          </div>
        </div>
        <p
          className="dim"
          style={{
            margin: 0,
            textAlign: "center",
            maxWidth: 380,
            fontSize: 12.5,
          }}
        >
          {t("signatures.customUnsignableHint")}
        </p>
      </div>
    );
  }

  // Backend-computed effective slots for THIS project (team mode: per-author
  // slots multiplied, applies_to/required_by on document INSTANCE ids). When
  // non-empty they replace the catalog defs, whose applies_to are pack
  // definition ids and would not match team doc instances like "vkr--ivanov".
  // Empty = old backend / solo: catalog slots, exactly as before.
  const runtimeSlots = state.runtime_slots;
  const allSlots =
    runtimeSlots.length > 0
      ? runtimeSlots
      : (versionDetail?.signatures.slots ?? []);
  const ownerBySlotId = new Map(
    runtimeSlots.map((s): [string, string | null] => [s.id, s.owner]),
  );
  const lang = project.lang ?? "ru";

  // "pdf": the custom file itself is the PDF (doc.output_file is repointed at
  // it server-side) — signable exactly like a template artifact, no extra
  // branching needed since getDocMeta already reads doc.output_file.
  // "convertible": no stable output PDF yet, only an optional preview_file
  // conversion — resolve the PDF surface from that instead.
  const isCustomConvertible = signability === "convertible";
  // Pass the doc so the PDF path comes from the API (team-aware).
  const pdfRelPath = isCustomConvertible
    ? (doc?.preview_file ?? "")
    : getDocMeta(docId, doc).out;
  // A live build that just finished, or the persisted last-compile record —
  // either being `success` means a PDF was produced. `locked` docs are kept
  // available so a finalised document can still be inspected/signed.
  // A custom convertible file's signable surface is its converted preview,
  // not a compile record — gate on preview_available instead.
  const hasBuild = isCustomConvertible
    ? (doc?.custom_file?.preview_available ?? false)
    : slot?.status === "success" ||
      lastCompile?.status === "success" ||
      doc?.status === "locked";

  const handlePlacementChange = (
    slotId: string,
    patch: UpdatePlacementRequest,
  ) => {
    updatePlacement({ projectId, docId, slotId, data: patch });
  };

  const goToProjectSignatures = () => {
    void navigate(`/projects/${projectId}/submit/signatures`);
  };

  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        display: "grid",
        // `minmax(0, 1fr)` (not the default `1fr` ≡ `minmax(auto, 1fr)`) lets the
        // preview column shrink below its content's intrinsic width, so the PDF
        // pane narrows with the layout instead of forcing an overflow.
        gridTemplateColumns: "300px minmax(0, 1fr)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          borderRight: "1px solid var(--border)",
          background: "var(--bg-1)",
          overflowY: "auto",
          minHeight: 0,
        }}
      >
        <DocPlacementPanel
          docId={docId}
          slotDefs={allSlots}
          state={state}
          lang={lang}
          currentPage={page}
          pageCount={pageCount}
          personNameForSlot={(slotId) =>
            personNameForSlot(
              slotId,
              project,
              ownerBySlotId.get(slotId) ?? null,
            )
          }
          onPlacementChange={handlePlacementChange}
          onJumpToPage={setPage}
          onOpenProjectSignatures={goToProjectSignatures}
        />
      </div>
      <div className="flex flex-col" style={{ minHeight: 0, minWidth: 0 }}>
        {isCustomConvertible && !hasBuild && (
          <div
            className="flex items-center gap-2"
            style={{
              padding: "10px 14px",
              borderBottom: "1px solid var(--border)",
              background: "var(--c-info-soft)",
              fontSize: 11.5,
              color: "var(--fg-1)",
            }}
          >
            <Info size={13} style={{ color: "var(--c-info)", flexShrink: 0 }} />
            <span>{t("signatures.customConvertiblePendingPreview")}</span>
          </div>
        )}
        <PdfStampEditor
          projectId={projectId}
          docId={docId}
          pdfRelPath={pdfRelPath}
          pdfAvailable={hasBuild}
          slotDefs={allSlots}
          state={state}
          page={page}
          onPageChange={setPage}
          onPageCountChange={setPageCount}
          onPlacementChange={handlePlacementChange}
          onCompileRequest={start}
          isCompileRunning={isRunning}
        />
      </div>
    </div>
  );
};
