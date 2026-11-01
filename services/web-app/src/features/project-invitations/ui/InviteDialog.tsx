import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { Button, CopyField, Input, Modal, Select, Textarea } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useProjectRoleLabel } from "@entities/project";
import {
  useCreateInvitation,
  type GrantRole,
  type ProjectInvitationCreated,
} from "@entities/invitation";
import { useFailureText } from "../lib/failure";
import { usePersonaOptions } from "../lib/personas";

const ROLES: readonly GrantRole[] = ["reader", "reviewer", "editor"];
const EXPIRY_DAYS = [1, 7, 14, 30] as const;

export type InvitePreset = {
  /** Существующий человек из кандидатов; без него приглашение идёт на почту. */
  user?: { id: string; name: string } | null;
  role?: GrantRole;
  persona?: string | null;
};

export type InviteDialogProps = {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
  preset?: InvitePreset | null;
  /** Командный проект: есть флаг «Правит всё». */
  isTeam?: boolean;
  /** Смотрящий владелец: только он выдаёт «Может делиться» и «Правит всё» без своих флагов. */
  isOwner?: boolean;
};

/** Форма приглашения (10.6): кандидат или почта, роль, персона, флаги, срок и сообщение. */
export const InviteDialog = (props: InviteDialogProps) => (
  // Новый ключ при каждом открытии сбрасывает форму к предустановке.
  <InviteDialogInner
    key={`${String(props.isOpen)}:${props.preset?.user?.id ?? ""}:${props.preset?.persona ?? ""}`}
    {...props}
  />
);

const InviteDialogInner = ({
  projectId,
  isOpen,
  onClose,
  preset = null,
  isTeam = false,
  isOwner = true,
}: InviteDialogProps) => {
  const { t } = useTranslation("invitations");
  const roleLabel = useProjectRoleLabel();
  const failureText = useFailureText();
  const personas = usePersonaOptions(projectId);
  const create = useCreateInvitation(projectId);
  const formId = useId();
  const user = preset?.user ?? null;
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<GrantRole>(preset?.role ?? "reviewer");
  const [persona, setPersona] = useState(preset?.persona ?? "");
  const [canShare, setCanShare] = useState(false);
  const [showSources, setShowSources] = useState(true);
  const [canEditAll, setCanEditAll] = useState(false);
  const [days, setDays] = useState<number>(7);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [manual, setManual] = useState<ProjectInvitationCreated | null>(null);

  const invitee = user?.name ?? email.trim();
  const ready = user !== null || /^\S+@\S+\.\S+$/.test(email.trim());

  const submit = () => {
    setError(null);
    create.mutate(
      {
        user_id: user?.id ?? null,
        email: user ? null : email.trim(),
        role,
        persona: persona === "" ? null : persona,
        can_share: role === "editor" && canShare,
        show_sources: role === "reader" ? showSources : true,
        can_edit_all: isTeam && role === "editor" && canEditAll,
        message: message.trim() === "" ? null : message.trim(),
        expires_in_days: days,
      },
      {
        onSuccess: (result) => {
          if (result.delivery === "manual" && result.link) {
            setManual(result);
            return;
          }
          toast.success(
            result.delivery === "email"
              ? t("form.sentEmail")
              : t("form.sentInbox", { name: invitee }),
          );
          onClose();
        },
        onError: (e) => {
          setError(failureText(failureCode(e)));
        },
      },
    );
  };

  if (manual?.link) {
    return (
      <Modal
        isOpen={isOpen}
        onClose={onClose}
        title={t("form.manualTitle")}
        footer={
          <Button type="button" onClick={onClose}>
            {t("form.done")}
          </Button>
        }
      >
        <div className="flex flex-col" style={{ gap: 12 }}>
          <Notice tone="warn" text={t("form.manualHint")} />
          <div data-testid="invite-link">
            <CopyField value={manual.link} label={t("form.linkLabel")} />
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      width={520}
      title={user ? t("form.titleUser", { name: user.name }) : t("form.title")}
      description={t("form.lead")}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("form.cancel")}
          </Button>
          <Button
            type="submit"
            form={formId}
            disabled={!ready || create.isPending}
            data-testid="invite-submit"
          >
            {t("form.submit")}
          </Button>
        </>
      }
    >
      <form
        id={formId}
        className="flex flex-col"
        style={{ gap: 12 }}
        data-testid="invite-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) submit();
        }}
      >
        {user === null && (
          <label className="flex flex-col" style={{ gap: 4, fontSize: 12 }}>
            {t("form.email")}
            <Input
              type="email"
              value={email}
              placeholder="petr@hse.ru"
              autoFocus
              onChange={(e) => {
                setEmail(e.target.value);
              }}
              data-testid="invite-email"
            />
          </label>
        )}
        <div className="flex" style={{ gap: 12, flexWrap: "wrap" }}>
          <div
            className="flex flex-col"
            style={{ gap: 4, fontSize: 12, flex: 1, minWidth: 160 }}
            data-testid="invite-role"
          >
            {t("form.role")}
            <Select
              ariaLabel={t("form.role")}
              value={role}
              options={ROLES.map((r) => ({ value: r, label: roleLabel(r) }))}
              onValueChange={(next) => {
                setRole(next as GrantRole);
              }}
            />
          </div>
          <div
            className="flex flex-col"
            style={{ gap: 4, fontSize: 12, flex: 1, minWidth: 160 }}
            data-testid="invite-persona"
          >
            {t("form.persona")}
            <Select
              ariaLabel={t("form.persona")}
              value={persona === "" ? "__none" : persona}
              options={personas.map((p) => ({
                value: p.value === "" ? "__none" : p.value,
                label: p.label,
              }))}
              onValueChange={(next) => {
                setPersona(next === "__none" ? "" : next);
              }}
            />
          </div>
        </div>
        <div className="flex flex-col" style={{ gap: 6, fontSize: 12 }}>
          {role === "reader" && (
            <Check
              checked={showSources}
              onChange={setShowSources}
              label={t("form.showSources")}
              testId="invite-show-sources"
            />
          )}
          {role === "editor" && (
            <Check
              checked={canShare}
              onChange={setCanShare}
              label={t("form.canShare")}
              testId="invite-can-share"
              disabled={!isOwner}
            />
          )}
          {role === "editor" && isTeam && (
            <Check
              checked={canEditAll}
              onChange={setCanEditAll}
              label={t("form.canEditAll")}
              testId="invite-can-edit-all"
              disabled={!isOwner}
            />
          )}
        </div>
        <div
          className="flex flex-col"
          style={{ gap: 4, fontSize: 12 }}
          data-testid="invite-expiry"
        >
          {t("form.expiry")}
          <Select
            ariaLabel={t("form.expiry")}
            value={String(days)}
            options={EXPIRY_DAYS.map((d) => ({
              value: String(d),
              label: t("form.days", { count: d }),
            }))}
            onValueChange={(next) => {
              setDays(Number(next));
            }}
          />
        </div>
        <label className="flex flex-col" style={{ gap: 4, fontSize: 12 }}>
          {t("form.message")}
          <Textarea
            value={message}
            maxLength={1000}
            rows={3}
            placeholder={t("form.messagePlaceholder")}
            onChange={(e) => {
              setMessage(e.target.value);
            }}
            data-testid="invite-message"
          />
        </label>
        {error && (
          <div role="alert" data-testid="invite-error">
            <Notice tone="err" text={error} />
          </div>
        )}
      </form>
    </Modal>
  );
};

const Check = ({
  checked,
  onChange,
  label,
  testId,
  disabled = false,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  testId: string;
  disabled?: boolean;
}) => (
  <label
    className="flex items-center"
    style={{ gap: 8, opacity: disabled ? 0.6 : 1 }}
  >
    <input
      type="checkbox"
      checked={checked}
      disabled={disabled}
      onChange={(e) => {
        onChange(e.target.checked);
      }}
      data-testid={testId}
    />
    {label}
  </label>
);
