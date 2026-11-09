import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast, useDebouncedValue, useThemeStore } from "@shared/lib";
import { Button, CopyField, Input, Modal, Select, Textarea } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useProjectRoleLabel } from "@entities/project";
import {
  useCreateInvitation,
  useInvitationDraft,
  type GrantRole,
  type ProjectInvitationCreated,
} from "@entities/invitation";
import { useFailureText } from "../lib/failure";
import { invitationText } from "../lib/invitationText";
import { usePersonaOptions } from "../lib/personas";

const ROLES: readonly GrantRole[] = ["reader", "reviewer", "editor"];
const EXPIRY_DAYS = [1, 7, 14, 30] as const;
const EMAIL_RE = /^\S+@\S+\.\S+$/;
const MESSAGE_MAX = 1000;
// Пауза после ввода почты, прежде чем пересобрать текст: не дёргать сервер на каждую букву.
const DRAFT_DEBOUNCE_MS = 400;

export type InvitePreset = {
  /** Существующий человек из кандидатов; без него приглашение идёт на почту. */
  user?: { id: string; name: string } | null;
  role?: GrantRole;
  persona?: string | null;
  /** Куда вести приглашённого после принятия (например, страница подписания маршрута). */
  next?: string | null;
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
  /** Приглашение создано (до показа ссылки): например, редактор маршрута ставит его в шаг. */
  onCreated?: (created: ProjectInvitationCreated) => void;
};

/**
 * Форма приглашения (10.6): кандидат или почта, роль, персона, флаги, срок и сообщение.
 * Сообщение заранее составлено сервером из данных проекта (по шаблону, без ИИ) и пересобирается при смене
 * адресата, роли и персоны, пока человек его не правил; «Вернуть исходный текст» снова берёт готовый.
 */
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
  onCreated,
}: InviteDialogProps) => {
  const { t } = useTranslation("invitations");
  const roleLabel = useProjectRoleLabel();
  const failureText = useFailureText();
  const personas = usePersonaOptions(projectId);
  const create = useCreateInvitation(projectId);
  const formId = useId();
  const lang = useThemeStore((s) => s.lang);
  const user = preset?.user ?? null;
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<GrantRole>(preset?.role ?? "reviewer");
  const [persona, setPersona] = useState(preset?.persona ?? "");
  const [canShare, setCanShare] = useState(false);
  const [showSources, setShowSources] = useState(true);
  const [canEditAll, setCanEditAll] = useState(false);
  const [days, setDays] = useState<number>(7);
  // null: человек текст не правил, показывается готовый с сервера.
  const [edited, setEdited] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [manual, setManual] = useState<{
    created: ProjectInvitationCreated;
    message: string | null;
  } | null>(null);

  const invitee = user?.name ?? email.trim();
  const ready = user !== null || EMAIL_RE.test(email.trim());
  const draftEmail = useDebouncedValue(email.trim(), DRAFT_DEBOUNCE_MS);
  const draft = useInvitationDraft(
    projectId,
    {
      user_id: user?.id ?? null,
      email: user === null && EMAIL_RE.test(draftEmail) ? draftEmail : null,
      role,
      persona: persona === "" ? null : persona,
    },
    lang,
    isOpen,
  );
  const original = draft.data?.message ?? "";
  const message = edited ?? original;
  const canReset = edited !== null && edited !== original;

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
        next: preset?.next ?? null,
      },
      {
        onSuccess: (result) => {
          onCreated?.(result);
          if (result.delivery === "manual" && result.link) {
            setManual({
              created: result,
              message: message.trim() === "" ? null : message.trim(),
            });
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

  if (manual?.created.link) {
    const link = manual.created.link;
    const copyInvitation = async () => {
      try {
        await navigator.clipboard.writeText(
          invitationText(manual.message, link),
        );
        toast.success(t("form.copied"));
      } catch {
        toast.error(t("form.copyFailed"));
      }
    };
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
        <div className="flex flex-col" style={{ gap: "0.75rem" }}>
          <Notice tone="warn" text={t("form.manualHint")} />
          {manual.message && (
            <div
              className="dim"
              style={{
                fontSize: "0.78125rem",
                whiteSpace: "pre-line",
                overflowWrap: "anywhere",
                maxHeight: "12rem",
                overflowY: "auto",
              }}
              data-testid="invite-manual-message"
            >
              {manual.message}
            </div>
          )}
          <div>
            <Button
              type="button"
              size="sm"
              onClick={() => {
                void copyInvitation();
              }}
              data-testid="invite-copy"
            >
              {t("form.copyInvitation")}
            </Button>
          </div>
          <div data-testid="invite-link">
            <CopyField value={link} label={t("form.linkLabel")} />
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
        style={{ gap: "0.75rem" }}
        data-testid="invite-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) submit();
        }}
      >
        {user === null && (
          <label
            className="flex flex-col"
            style={{ gap: "0.25rem", fontSize: "0.75rem" }}
          >
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
        <div className="flex" style={{ gap: "0.75rem", flexWrap: "wrap" }}>
          <div
            className="flex flex-col"
            style={{
              gap: "0.25rem",
              fontSize: "0.75rem",
              flex: 1,
              minWidth: "10rem",
            }}
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
            style={{
              gap: "0.25rem",
              fontSize: "0.75rem",
              flex: 1,
              minWidth: "10rem",
            }}
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
        <div
          className="flex flex-col"
          style={{ gap: "0.375rem", fontSize: "0.75rem" }}
        >
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
          style={{ gap: "0.25rem", fontSize: "0.75rem" }}
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
        <div
          className="flex flex-col"
          style={{ gap: "0.25rem", fontSize: "0.75rem" }}
        >
          <div
            className="flex items-center"
            style={{ gap: "0.5rem", justifyContent: "space-between" }}
          >
            <label htmlFor={`${formId}-message`}>{t("form.message")}</label>
            {canReset && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEdited(null);
                }}
                data-testid="invite-message-reset"
              >
                {t("form.messageReset")}
              </Button>
            )}
          </div>
          <Textarea
            id={`${formId}-message`}
            value={message}
            maxLength={MESSAGE_MAX}
            rows={7}
            placeholder={t("form.messagePlaceholder")}
            onChange={(e) => {
              setEdited(e.target.value);
            }}
            data-testid="invite-message"
          />
          {original !== "" && (
            <span className="dim" data-testid="invite-message-hint">
              {t("form.messageHint")}
            </span>
          )}
        </div>
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
    style={{ gap: "0.5rem", opacity: disabled ? 0.6 : 1 }}
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
