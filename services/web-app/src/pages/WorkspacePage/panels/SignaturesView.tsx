import { Info, PenTool } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";
import { useSignaturesState } from "@entities/signature";
import { useVersionDetail } from "@entities/template-catalog";
import { SlotPanel } from "@features/signature-stamper";
import { Spinner } from "@shared/ui/Spinner";
import { PageHead } from "./PageHead";

type Project = z.infer<typeof ProjectResponseSchema>;

export type SignaturesViewProps = {
  project: Project;
};

const personNameForSlot = (
  slotId: string,
  project: Project,
  owner: string | null,
): string | null => {
  // Team runtime slots carry the owner's slug — the signer is that author.
  if (owner != null) {
    return project.authors?.find((a) => a.slug === owner)?.name ?? null;
  }
  if (slotId === "author") return project.authors?.[0]?.name ?? null;
  if (slotId === "supervisor") return project.supervisor?.name ?? null;
  if (slotId === "co_supervisor") return project.co_supervisor?.name ?? null;
  return null;
};

export const SignaturesView = ({ project }: SignaturesViewProps) => {
  const { t } = useTranslation("workspace");
  const { data: versionDetail, isLoading: vdLoading } = useVersionDetail(
    project.lock.pack_id,
    project.lock.template_id,
    project.lock.version,
  );
  const { data: state, isLoading: stateLoading } = useSignaturesState(
    project.id,
  );

  if (vdLoading || stateLoading || !state) {
    return (
      <div
        style={{
          padding: "24px 32px",
          flex: 1,
          minHeight: 0,
          display: "flex",
          justifyContent: "center",
        }}
      >
        <Spinner />
      </div>
    );
  }

  // Backend-computed effective slots for THIS project (team mode: per-author
  // slots multiplied — "author--ivanov", label already carries the name — and
  // applies_to/required_by reference document INSTANCE ids). When non-empty
  // they replace the catalog defs, whose applies_to are pack definition ids
  // and would not match team doc instances. Empty = old backend / solo: keep
  // the catalog slots exactly as before.
  const runtimeSlots = state.runtime_slots;
  const slots =
    runtimeSlots.length > 0
      ? runtimeSlots
      : (versionDetail?.signatures.slots ?? []);
  const ownerBySlotId = new Map(
    runtimeSlots.map((s): [string, string | null] => [s.id, s.owner]),
  );
  const lang = project.lang ?? "ru";

  return (
    <div
      style={{
        padding: "24px 32px",
        overflowY: "auto",
        flex: 1,
        minHeight: 0,
      }}
    >
      <PageHead
        icon={PenTool}
        title={t("signatures.title")}
        sub={t("signatures.subtitle")}
      />

      {slots.length === 0 ? (
        <div
          className="card"
          style={{
            marginTop: 20,
            padding: 18,
            color: "var(--fg-2)",
            fontSize: 12,
          }}
        >
          {t("signatures.noSlots")}
        </div>
      ) : (
        <div style={{ marginTop: 20 }}>
          <SlotPanel
            projectId={project.id}
            slotDefs={slots}
            state={state}
            lang={lang}
            personNameForSlot={(slotId) =>
              personNameForSlot(
                slotId,
                project,
                ownerBySlotId.get(slotId) ?? null,
              )
            }
          />
        </div>
      )}

      <div className="card" style={{ marginTop: 16, padding: 14 }}>
        <div className="flex items-center gap-2" style={{ marginBottom: 6 }}>
          <Info size={12} style={{ color: "var(--c-info)" }} />
          <strong style={{ fontSize: 12 }}>{t("signatures.howItWorks")}</strong>
        </div>
        <ul
          className="dim"
          style={{
            margin: 0,
            paddingLeft: 18,
            fontSize: 11.5,
            lineHeight: 1.6,
          }}
        >
          <li>{t("signatures.howItWorksItem1")}</li>
          <li>{t("signatures.howItWorksItem2")}</li>
          <li>{t("signatures.howItWorksItem3")}</li>
        </ul>
      </div>

      <div className="card" style={{ marginTop: 16, padding: 14 }}>
        <div className="flex items-center gap-2" style={{ marginBottom: 6 }}>
          <Info size={12} style={{ color: "var(--c-info)" }} />
          <strong style={{ fontSize: 12 }}>
            {t("signatures.whereStored")}
          </strong>
        </div>
        <p
          className="dim mono"
          style={{ margin: 0, fontSize: 11, lineHeight: 1.6 }}
        >
          {project.folder}/.hse-studio/signatures/
        </p>
      </div>
    </div>
  );
};
