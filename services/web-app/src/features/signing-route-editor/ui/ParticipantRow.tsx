import { useTranslation } from "react-i18next";
import { GripVertical, MailPlus } from "lucide-react";
import type {
  RouteParticipant,
  RoutePersonOption,
  SigningRoutePreview,
} from "@entities/signing-route";
import { ActionMenu, type ActionMenuItem } from "@shared/ui";
import { MEMBERSHIP_TONE } from "../lib/labels";

type PreviewPerson = SigningRoutePreview["participants"][number];

export type ParticipantRowProps = {
  participant: RouteParticipant;
  preview: PreviewPerson | undefined;
  personaLabel: string;
  isMe: boolean;
  editable: boolean;
  busy: boolean;
  /**
   * Из кого выбрать человека на эту персону: участники проекта с ней и ожидающие приглашения
   * (`candidates` хода маршрута), без тех, кто уже стоит в маршруте на этой персоне.
   */
  options: readonly RoutePersonOption[];
  registrationClosed: boolean;
  menu: readonly ActionMenuItem[];
  onDragStart: () => void;
  onDragEnd: () => void;
  onInvite: () => void;
  onPick: (option: RoutePersonOption) => void;
};

const optionValue = (option: RoutePersonOption): string =>
  `${option.kind}:${option.id}`;

/** Человек в шаге: кто он, есть ли в проекте, чем подпишет, готов ли и сколько у него действий. */
export const ParticipantRow = ({
  participant: p,
  preview,
  personaLabel,
  isMe,
  editable,
  busy,
  options,
  registrationClosed,
  menu,
  onDragStart,
  onDragEnd,
  onInvite,
  onPick,
}: ParticipantRowProps) => {
  const { t } = useTranslation("signingRouteEditor");
  const membership = preview?.membership ?? p.membership;
  const current =
    p.user_id !== null
      ? `member:${p.user_id}`
      : p.invitation_id !== null
        ? `invitation:${p.invitation_id}`
        : "";
  // Выбор нужен, когда людей на персону несколько или человека ещё нет, а взять есть из кого.
  const canPick =
    editable &&
    (membership === "missing" ? options.length > 0 : options.length > 1);
  const optionLabel = (option: RoutePersonOption): string => {
    const name = option.name ?? t("person.unnamed");
    return option.kind === "invitation"
      ? t("person.optionInvited", { name })
      : name;
  };
  const method = preview?.method ?? p.method;
  const actions = preview?.actions;

  const readiness = (() => {
    if (!preview || method === null) return null;
    if (preview.chooses_method) return t("person.choosesMethod");
    if (method === "image")
      return preview.image_ready
        ? t("person.imageReady")
        : isMe
          ? t("person.imageMissing")
          : t("person.imageLater");
    return preview.plate_ready
      ? t("person.plateReady")
      : isMe
        ? t("person.plateMissing")
        : t("person.plateLater");
  })();

  const actionsText =
    actions === undefined
      ? null
      : actions === 0
        ? t("person.actionsZero")
        : actions === 1
          ? t("person.actionsOne")
          : t("person.actionsTwo");

  return (
    <div
      className="flex items-start"
      style={{
        gap: "0.5rem",
        padding: "0.5rem 0.625rem",
        borderRadius: "var(--r-2)",
        border: "1px solid var(--border)",
        background: "var(--bg-0)",
      }}
      draggable={editable && !busy}
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", p.id);
        e.dataTransfer.effectAllowed = "move";
        onDragStart();
      }}
      onDragEnd={onDragEnd}
      data-testid={`route-person-${p.persona}`}
    >
      {editable && (
        <GripVertical
          size="0.875rem"
          aria-hidden="true"
          style={{
            color: "var(--fg-3)",
            cursor: "grab",
            marginTop: "0.125rem",
          }}
        />
      )}
      <div
        className="flex flex-col"
        style={{ flex: 1, minWidth: 0, gap: "0.25rem" }}
      >
        <div
          className="flex items-center"
          style={{ gap: "0.375rem", flexWrap: "wrap" }}
        >
          <strong style={{ fontSize: "0.8125rem", overflowWrap: "anywhere" }}>
            {p.name ??
              (membership === "invited" ? (
                // Приглашение без имени и адреса: человек назначен, просто ещё не принял.
                t("person.invitee")
              ) : (
                <span style={{ color: "var(--c-warn)" }}>
                  {t("person.nobody")}
                </span>
              ))}
            {isMe && <span className="dim"> ({t("person.you")})</span>}
          </strong>
          <span className="dim" style={{ fontSize: "0.71875rem" }}>
            {personaLabel}
          </span>
        </div>
        <div
          className="flex items-center"
          style={{
            gap: "0.375rem",
            flexWrap: "wrap",
            fontSize: "0.6875rem",
            color: "var(--fg-2)",
          }}
        >
          <span
            className="chip subtle"
            style={{ color: MEMBERSHIP_TONE[membership] }}
          >
            {t(`person.membership.${membership}`)}
          </span>
          <span className="chip subtle">
            {method === null ? t("person.approverOnly") : t(`method.${method}`)}
          </span>
          {readiness && <span>{readiness}</span>}
          {actionsText && (
            <span
              style={{ color: actions === 2 ? "var(--c-warn)" : undefined }}
            >
              · {actionsText}
            </span>
          )}
        </div>
        {(canPick || (editable && membership === "missing")) && (
          <div
            className="flex items-center"
            style={{ gap: "0.5rem", flexWrap: "wrap", marginTop: "0.125rem" }}
          >
            {canPick && (
              <select
                className="input"
                style={{
                  width: "auto",
                  maxWidth: "100%",
                  minWidth: 0,
                  fontSize: "0.6875rem",
                  padding: "0.125rem 0.375rem",
                }}
                aria-label={t("person.pick", { persona: personaLabel })}
                value={
                  options.some((o) => optionValue(o) === current) ? current : ""
                }
                disabled={busy}
                onChange={(e) => {
                  const picked = options.find(
                    (o) => optionValue(o) === e.target.value,
                  );
                  if (picked && e.target.value !== current) onPick(picked);
                }}
                data-testid={`route-pick-${p.persona}`}
              >
                {!options.some((o) => optionValue(o) === current) && (
                  <option value="">{t("person.pickPlaceholder")}</option>
                )}
                {options.map((option) => (
                  <option key={optionValue(option)} value={optionValue(option)}>
                    {optionLabel(option)}
                  </option>
                ))}
              </select>
            )}
            {membership === "missing" && (
              <button
                type="button"
                className="btn xs primary"
                disabled={busy}
                onClick={onInvite}
                data-testid="route-invite"
              >
                <MailPlus size="0.6875rem" aria-hidden="true" />
                {t("person.invite")}
              </button>
            )}
            {membership === "missing" && registrationClosed && (
              <span className="dim" style={{ fontSize: "0.65625rem" }}>
                {t("person.registrationClosed")}
              </span>
            )}
          </div>
        )}
      </div>
      {editable && menu.length > 0 && (
        <ActionMenu
          items={menu.map((item) => ({
            ...item,
            disabled: busy || item.disabled === true,
          }))}
          label={t("steps.personActions", { name: p.name ?? personaLabel })}
        />
      )}
    </div>
  );
};
