import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp, GripVertical, Plus } from "lucide-react";
import type { ProjectInvitation } from "@entities/invitation";
import type {
  SigningRoute,
  SigningRoutePreview,
} from "@entities/signing-route";
import { InviteDialog } from "@features/project-invitations";
import {
  addApprover,
  draftOf,
  joinPrevious,
  movePerson,
  moveStep,
  removePerson,
  separate,
  setPerson,
  type DraftSteps,
} from "../model/routeDraft";
import { ParticipantRow } from "./ParticipantRow";

export type RouteStepsCardProps = {
  projectId: string;
  route: SigningRoute;
  preview: SigningRoutePreview | undefined;
  editable: boolean;
  /** Правка сохраняется: управление видно, но не нажимается. */
  busy: boolean;
  meId: string | null;
  personaLabel: (persona: string) => string;
  /** Персоны, которые можно взять в согласующие (без уже стоящих в маршруте). */
  approverPersonas: readonly string[];
  invitations: readonly ProjectInvitation[];
  registrationClosed: boolean;
  onChange: (steps: DraftSteps) => void;
};

type Drag = { kind: "person"; id: string } | { kind: "step"; index: number };

/**
 * «Кто и в каком порядке»: шаги карточками, внутри шага параллельно. Людей и шаги можно
 * перетаскивать; то же самое есть кнопками (меню человека, стрелки шага) для клавиатуры.
 */
export const RouteStepsCard = ({
  projectId,
  route,
  preview,
  editable,
  busy,
  meId,
  personaLabel,
  approverPersonas,
  invitations,
  registrationClosed,
  onChange,
}: RouteStepsCardProps) => {
  const { t } = useTranslation("signingRouteEditor");
  const [drag, setDrag] = useState<Drag | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [inviting, setInviting] = useState<{
    id: string;
    persona: string;
  } | null>(null);
  const [approver, setApprover] = useState("");
  const steps = draftOf(route).steps;
  const previewOf = new Map(
    (preview?.participants ?? []).map((p) => [p.participant_id, p]),
  );
  const visualStep = preview?.visual_step ?? null;
  const canEdit = editable && !busy;

  const endDrag = () => {
    setDrag(null);
    setOver(null);
  };

  const dropOnStep = (index: number) => {
    if (!drag || !canEdit) {
      endDrag();
      return;
    }
    const next: DraftSteps =
      drag.kind === "person"
        ? movePerson(steps, drag.id, { step: index, newStep: false })
        : moveStep(steps, drag.index, index);
    endDrag();
    if (next !== steps) onChange(next);
  };

  const dropInGap = (gap: number) => {
    if (!drag || !canEdit) {
      endDrag();
      return;
    }
    const next: DraftSteps =
      drag.kind === "person"
        ? movePerson(steps, drag.id, { step: gap, newStep: true })
        : moveStep(steps, drag.index, gap > drag.index ? gap - 1 : gap);
    endDrag();
    if (next !== steps) onChange(next);
  };

  const target = (key: string, onDrop: () => void) => ({
    onDragOver: (e: React.DragEvent) => {
      if (!drag) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      if (over !== key) setOver(key);
    },
    onDragLeave: () => {
      if (over === key) setOver(null);
    },
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      onDrop();
    },
  });

  const gap = (index: number) =>
    drag && canEdit ? (
      <div
        key={`gap-${String(index)}`}
        {...target(`gap-${String(index)}`, () => {
          dropInGap(index);
        })}
        data-testid={`route-gap-${String(index)}`}
        style={{
          border: "1px dashed var(--border-strong)",
          borderRadius: "var(--r-2)",
          padding: "0.375rem",
          textAlign: "center",
          fontSize: "0.6875rem",
          color: "var(--fg-2)",
          background:
            over === `gap-${String(index)}` ? "var(--accent-soft)" : undefined,
        }}
      >
        {t("steps.dropNew")}
      </div>
    ) : null;

  return (
    <div className="flex flex-col" style={{ gap: "0.5rem" }}>
      <p className="dim" style={{ margin: 0, fontSize: "0.71875rem" }}>
        {editable ? t("steps.hint") : t("steps.hintReadOnly")}
      </p>
      {gap(0)}
      {route.steps.map((people, index) => {
        const key = `step-${String(index)}`;
        return (
          <div key={people.map((p) => p.id).join(",")}>
            <section
              aria-label={t("steps.step", { n: index + 1 })}
              data-testid={`route-step-${String(index + 1)}`}
              {...(editable
                ? target(key, () => {
                    dropOnStep(index);
                  })
                : {})}
              className="flex flex-col"
              style={{
                gap: "0.375rem",
                padding: "0.625rem",
                borderRadius: "var(--r-3, 0.5rem)",
                border: "1px solid var(--border)",
                background: over === key ? "var(--accent-soft)" : "var(--bg-1)",
              }}
            >
              <div className="flex items-center" style={{ gap: "0.375rem" }}>
                {editable && (
                  <span
                    draggable={canEdit}
                    onDragStart={(e) => {
                      e.dataTransfer.setData("text/plain", key);
                      e.dataTransfer.effectAllowed = "move";
                      setDrag({ kind: "step", index });
                    }}
                    onDragEnd={endDrag}
                    style={{ cursor: "grab", color: "var(--fg-3)" }}
                    aria-hidden="true"
                    data-testid={`route-step-handle-${String(index + 1)}`}
                  >
                    <GripVertical size="0.875rem" />
                  </span>
                )}
                <strong style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>
                  {t("steps.step", { n: index + 1 })}
                </strong>
                {people.length > 1 && (
                  <span className="dim" style={{ fontSize: "0.6875rem" }}>
                    {t("steps.parallel")}
                  </span>
                )}
                {visualStep !== null &&
                  visualStep > 0 &&
                  index + 1 === visualStep && (
                    <span
                      className="chip subtle"
                      title={t("steps.freezeAfterTitle")}
                    >
                      {t("steps.freezeAfter")}
                    </span>
                  )}
                {editable && (
                  <span
                    className="flex items-center"
                    style={{ marginLeft: "auto", gap: "0.125rem" }}
                  >
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={t("steps.up", { n: index + 1 })}
                      disabled={busy || index === 0}
                      onClick={() => {
                        onChange(moveStep(steps, index, index - 1));
                      }}
                    >
                      <ChevronUp size="0.875rem" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={t("steps.down", { n: index + 1 })}
                      disabled={busy || index === route.steps.length - 1}
                      onClick={() => {
                        onChange(moveStep(steps, index, index + 1));
                      }}
                    >
                      <ChevronDown size="0.875rem" aria-hidden="true" />
                    </button>
                  </span>
                )}
              </div>
              {people.map((p) => (
                <ParticipantRow
                  key={p.id}
                  participant={p}
                  preview={previewOf.get(p.id)}
                  personaLabel={personaLabel(p.persona)}
                  isMe={meId !== null && p.user_id === meId}
                  editable={editable}
                  busy={busy}
                  invitations={invitations.filter(
                    (inv) => inv.persona === p.persona,
                  )}
                  registrationClosed={registrationClosed}
                  menu={[
                    {
                      id: "join",
                      label: t("steps.joinPrevious"),
                      disabled: index === 0,
                      onSelect: () => {
                        onChange(joinPrevious(steps, p.id));
                      },
                    },
                    {
                      id: "separate",
                      label: t("steps.separate"),
                      disabled: people.length < 2,
                      onSelect: () => {
                        onChange(separate(steps, p.id));
                      },
                    },
                    // Владельца слотов не убрать: его подписи остались бы без подписанта.
                    ...(p.assignments.length === 0
                      ? [
                          {
                            id: "remove",
                            label: t("steps.remove"),
                            danger: true,
                            onSelect: () => {
                              onChange(removePerson(steps, p.id));
                            },
                          },
                        ]
                      : []),
                  ]}
                  onDragStart={() => {
                    setDrag({ kind: "person", id: p.id });
                  }}
                  onDragEnd={endDrag}
                  onInvite={() => {
                    setInviting({ id: p.id, persona: p.persona });
                  }}
                  onPickInvitation={(invitationId) => {
                    onChange(
                      setPerson(steps, p.id, {
                        user_id: null,
                        invitation_id: invitationId,
                      }),
                    );
                  }}
                />
              ))}
            </section>
            <div style={{ marginTop: "0.5rem" }}>{gap(index + 1)}</div>
          </div>
        );
      })}

      {(preview?.participants ?? []).some((p) => p.actions === 2) && (
        <p className="dim" style={{ margin: 0, fontSize: "0.6875rem" }}>
          {t("steps.imageFirst")}
        </p>
      )}

      {editable && approverPersonas.length > 0 && (
        <div
          className="flex items-center"
          style={{ gap: "0.5rem", flexWrap: "wrap" }}
        >
          <select
            className="input"
            style={{
              width: "auto",
              minWidth: "12rem",
              fontSize: "0.75rem",
              padding: "0.3125rem 0.5rem",
            }}
            aria-label={t("steps.approverPersona")}
            value={approver}
            disabled={busy}
            onChange={(e) => {
              setApprover(e.target.value);
            }}
            data-testid="route-approver-persona"
          >
            <option value="">{t("steps.approverPersona")}</option>
            {approverPersonas.map((persona) => (
              <option key={persona} value={persona}>
                {personaLabel(persona)}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn sm"
            disabled={busy || approver === ""}
            onClick={() => {
              onChange(addApprover(steps, approver));
              setApprover("");
            }}
            data-testid="route-add-approver"
          >
            <Plus size="0.75rem" aria-hidden="true" />
            {t("steps.addApprover")}
          </button>
        </div>
      )}

      {inviting && (
        <InviteDialog
          projectId={projectId}
          isOpen
          onClose={() => {
            setInviting(null);
          }}
          // Заготовка как у «Пригласить научрука»: роль Рецензент и персона шага.
          preset={{ role: "reviewer", persona: inviting.persona }}
          onCreated={(created) => {
            onChange(
              setPerson(steps, inviting.id, {
                user_id: null,
                invitation_id: created.invitation.id,
              }),
            );
          }}
        />
      )}
    </div>
  );
};
