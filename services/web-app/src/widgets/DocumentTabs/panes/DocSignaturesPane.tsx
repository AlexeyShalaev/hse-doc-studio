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
import { useBootstrap } from "@entities/session";
import {
  useDocSignaturePlan,
  useReleaseWithheld,
  useSetSlotOptional,
  useSignaturesState,
  useUpdateSignaturePlacement,
} from "@entities/signature";
import { useUpdateSlotConfig } from "@entities/signing-identity";
import { useVersionDetail } from "@entities/template-catalog";
import { DocPlacementPanel, PdfStampEditor } from "@features/signature-stamper";
import { SignedVersionPanel } from "@features/signing-version";
import type { SignMode, UpdatePlacementRequest } from "@shared/api/types";
import { ApiError, failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { Notice } from "@shared/ui";
import { Spinner } from "@shared/ui/Spinner";

export type DocSignaturesPaneProps = {
  projectId: string;
  docId: string;
  /**
   * Документ на подписании по маршруту: подписи менять нельзя (docs/design/signing-route.md,
   * 5.5). Панель слотов и рамки на странице только для просмотра.
   */
  locked?: boolean;
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
  if (slotId === "academic_supervisor")
    return project.academic_supervisor?.name ?? null;
  return null;
};

export const DocSignaturesPane = ({
  projectId,
  docId,
  locked = false,
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
  const { mutate: updateSlotConfig } = useUpdateSlotConfig();
  const { mutate: releaseWithheld } = useReleaseWithheld();
  const setOptional = useSetSlotOptional();
  // «Подпись уже стоит» (signing-route.md, 13.9): статус слота в плане документа, пока его держит
  // маршрут. Маршруты есть только на сервере.
  const boot = useBootstrap().data;
  const isServer = boot?.mode === "server";
  const { data: docPlan } = useDocSignaturePlan(projectId, docId, {
    enabled: isServer && boot.user !== null,
  });
  const { start, isRunning, slot, block } = useStartCompile(projectId, docId);

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
        style={{ padding: "2rem", flex: 1, minHeight: 0 }}
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
        style={{ flex: 1, padding: "2.5rem", gap: "1rem", minHeight: 0 }}
      >
        <div
          className="stripes flex items-center justify-center"
          style={{
            width: "13.75rem",
            height: "17.5rem",
            borderRadius: "0.375rem",
            border: "1px solid var(--border-strong)",
            color: "var(--fg-3)",
          }}
        >
          <div
            className="flex flex-col items-center"
            style={{ gap: "0.375rem" }}
          >
            <ShieldOff size="1.75rem" />
          </div>
        </div>
        <p
          className="dim"
          style={{
            margin: 0,
            textAlign: "center",
            maxWidth: "23.75rem",
            fontSize: "0.78125rem",
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

  // Картинка ↔ открепленная ЭП. Ключ подписи (PAdES) при смене режима
  // сбрасывается: эти режимы взаимоисключающи.
  const handleSlotModeChange = (slotId: string, mode: SignMode) => {
    updateSlotConfig({
      projectId,
      slotId,
      data: { signing_identity_id: null, sign_mode: mode, sign_reason: "" },
    });
  };

  // «Показать» картинку, придержанную маршрутом (docs/design/signing-route.md, 5.6): картинка
  // встанет в документ без согласия подписанта, поэтому спрашиваем.
  const handleReleaseWithheld = (slotId: string) => {
    if (!window.confirm(t("signatureStamper:docPlacement.withheldConfirm")))
      return;
    releaseWithheld(
      { projectId, docId, slotId },
      {
        onSuccess: () => {
          toast.success(t("signatureStamper:docPlacement.withheldShown"));
        },
        onError: (err) => {
          toast.error(
            t("signatureStamper:docPlacement.withheldFailed", {
              reason: err.message,
            }),
          );
        },
      },
    );
  };

  // «Подпись необязательна» (signing-route.md, 13.9): отмечают те, кто отправляет на подписание;
  // локально владелец.
  const canEditOptional =
    !isServer || project.my_role === "owner" || project.my_role === "editor";
  const heldByRoute = docPlan?.route != null;
  const optionalErrorText = (error: unknown): string => {
    const code = failureCode(error);
    const known: Record<string, string> = {
      optional_forbidden: t("signatureStamper:docPlacement.optional.required"),
      slot_signed: t("signatureStamper:docPlacement.optional.signed"),
      forbidden: t("signatureStamper:docPlacement.optional.noRights"),
      unknown_slot: t("signatureStamper:docPlacement.optional.unknownSlot"),
    };
    return (
      known[code] ??
      (error instanceof ApiError && error.detail !== ""
        ? error.detail
        : error instanceof Error
          ? error.message
          : String(error))
    );
  };
  const optionalControl = {
    canEdit: canEditOptional,
    isSigned: (slotId: string) =>
      heldByRoute &&
      (docPlan.docs
        .find((d) => d.doc_id === docId)
        ?.slots.some((s) => s.slot_id === slotId && s.status === "signed") ??
        false),
    isPending: (slotId: string, profileId: string) =>
      setOptional.isPending &&
      setOptional.variables.slotId === slotId &&
      setOptional.variables.profileId === profileId,
    onChange: (slotId: string, profileId: string, optional: boolean) => {
      setOptional.mutate(
        { projectId, docId, slotId, profileId, optional },
        {
          onError: (err) => {
            toast.error(
              t("signatureStamper:docPlacement.optional.failed", {
                reason: optionalErrorText(err),
              }),
            );
          },
        },
      );
    },
  };

  const goToProjectSignatures = () => {
    void navigate(`/projects/${projectId}/submit/signatures`);
  };

  return (
    <div
      className="doc-signatures-grid"
      style={{
        flex: 1,
        minHeight: 0,
        display: "grid",
        // `minmax(0, 1fr)` (not the default `1fr` ≡ `minmax(auto, 1fr)`) lets the
        // preview column shrink below its content's intrinsic width, so the PDF
        // pane narrows with the layout instead of forcing an overflow.
        gridTemplateColumns: "18.75rem minmax(0, 1fr)",
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
        {/* Версия на подписи (signing-route.md, 12.8): что подписывают и как вернуться к сборке. */}
        <SignedVersionPanel projectId={projectId} docId={docId} />
        {locked && (
          <div style={{ padding: "0.75rem 0.75rem 0" }}>
            <Notice
              tone="info"
              role="status"
              text={t("signingProgress:hold.locked")}
            />
          </div>
        )}
        {/* На подписании панель видна, правки слотов закрыты (inert внутри панели), открыта
            только отметка «Подпись необязательна». */}
        <div data-testid="doc-signatures-panel">
          <DocPlacementPanel
            projectId={projectId}
            docId={docId}
            pdfAvailable={hasBuild}
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
            onSlotModeChange={handleSlotModeChange}
            onReleaseWithheld={handleReleaseWithheld}
            routeHeld={locked}
            locked={locked}
            optionalControl={optionalControl}
          />
        </div>
      </div>
      <div className="flex flex-col" style={{ minHeight: 0, minWidth: 0 }}>
        {isCustomConvertible && !hasBuild && (
          <div
            className="flex items-center gap-2"
            style={{
              padding: "0.625rem 0.875rem",
              borderBottom: "1px solid var(--border)",
              background: "var(--c-info-soft)",
              fontSize: "0.71875rem",
              color: "var(--fg-1)",
            }}
          >
            <Info
              size="0.8125rem"
              style={{ color: "var(--c-info)", flexShrink: 0 }}
            />
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
          readOnly={locked}
          onCompileRequest={start}
          isCompileRunning={isRunning}
          isCompileBlocked={block !== null}
        />
      </div>
    </div>
  );
};
