import { useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type {
  CreateShareLinkRequest,
  LinkRole,
  ShareLink,
  ShareLinkVisit,
  UpdateShareLinkRequest,
} from "@entities/share-link";
import { Button, CopyField, Input, Modal, Select, Spinner } from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import { localeTag } from "@shared/lib";
import { Notice } from "@shared/ui/ConflictKit";
import { formatLinkDate } from "../lib/format";

const LINK_ROLES: readonly LinkRole[] = ["reader", "reviewer", "editor"];
const EXPIRY_CHOICES = [7, 30, 60, 365] as const;
const LABEL_MAX = 128;
const PASSWORD_MIN = 8;
const PASSWORD_MAX = 128;
const NONE = "none";
const KEEP = "keep";

export type ShareLinkFormValue =
  | { mode: "create"; body: CreateShareLinkRequest }
  | { mode: "edit"; body: UpdateShareLinkRequest };

export type ShareLinkFormProps = {
  isOpen: boolean;
  /** Правка: ссылка, иначе создание. */
  link: ShareLink | null;
  /** Старшая роль, которую можно дать ссылкой (роль создателя и политика). */
  maxRole: LinkRole;
  /** Вход обязателен политикой (NDA или «только участникам организации»). */
  forcedLogin: boolean;
  pending?: boolean;
  error?: string | null;
  onSubmit: (value: ShareLinkFormValue) => void;
  onClose: () => void;
};

const roleRank = (role: LinkRole): number => LINK_ROLES.indexOf(role);

/** Диалог создания и правки ссылки (`share-link-form`). */
export const ShareLinkForm = (props: ShareLinkFormProps) => {
  const { t } = useTranslation("shareLinks");
  const { link } = props;
  const editing = link !== null;
  const ids = {
    label: useId(),
    role: useId(),
    password: useId(),
    expiry: useId(),
  };
  const [label, setLabel] = useState(link?.label ?? "");
  const [role, setRole] = useState<LinkRole>(link?.role ?? "reader");
  const [sources, setSources] = useState(link?.show_sources ?? false);
  const [requireLogin, setRequireLogin] = useState(
    link?.require_login ?? props.forcedLogin,
  );
  const [password, setPassword] = useState("");
  const [clearPassword, setClearPassword] = useState(false);
  const [expiry, setExpiry] = useState<string>(
    editing ? (link.state === "expired" ? "30" : KEEP) : "60",
  );

  const labelValid = label.trim().length > 0 && label.length <= LABEL_MAX;
  const passwordValid =
    password === "" ||
    (password.length >= PASSWORD_MIN && password.length <= PASSWORD_MAX);
  const valid = labelValid && passwordValid;

  const expiryOptions = [
    ...(editing ? [{ value: KEEP, label: t("form.expiryKeep") }] : []),
    { value: NONE, label: t("form.expiryNone") },
    ...EXPIRY_CHOICES.map((days) => ({
      value: String(days),
      label: t("form.expiryDays", { count: days }),
    })),
  ];

  const submit = () => {
    if (!valid) return;
    const days = expiry === NONE || expiry === KEEP ? null : Number(expiry);
    const effectiveSources = role === "reader" ? sources : true;
    if (!editing) {
      props.onSubmit({
        mode: "create",
        body: {
          label: label.trim(),
          role,
          show_sources: effectiveSources,
          require_login: requireLogin || props.forcedLogin,
          password: password === "" ? null : password,
          expires_in_days: days,
        },
      });
      return;
    }
    props.onSubmit({
      mode: "edit",
      body: {
        label: label.trim() === link.label ? null : label.trim(),
        role: role === link.role ? null : role,
        show_sources:
          effectiveSources === link.show_sources ? null : effectiveSources,
        require_login:
          requireLogin === link.require_login ? null : requireLogin,
        password: password === "" ? null : password,
        clear_password: clearPassword && password === "",
        expires_in_days: days,
        clear_expiry: expiry === NONE && link.expires_at !== null,
      },
    });
  };

  return (
    <Modal
      isOpen={props.isOpen}
      onClose={() => {
        if (!props.pending) props.onClose();
      }}
      title={editing ? t("form.editTitle") : t("form.createTitle")}
      width={520}
      footer={
        <>
          <Button
            type="button"
            variant="ghost"
            onClick={props.onClose}
            disabled={props.pending}
          >
            {t("form.cancel")}
          </Button>
          <Button
            type="submit"
            form="share-link-form"
            disabled={!valid || props.pending}
            data-testid="share-link-submit"
          >
            {props.pending && <Spinner size="sm" />}
            {editing ? t("form.submitSave") : t("form.submitCreate")}
          </Button>
        </>
      }
    >
      <form
        id="share-link-form"
        className="share-link-form"
        data-testid="share-link-form"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <Input
          id={ids.label}
          label={t("form.label")}
          placeholder={t("form.labelPlaceholder")}
          hint={t("form.labelHint")}
          value={label}
          maxLength={LABEL_MAX}
          onChange={(event) => {
            setLabel(event.target.value);
          }}
          data-testid="share-link-label"
          autoFocus
        />
        <div className="share-link-field">
          <label htmlFor={ids.role}>{t("form.role")}</label>
          <div data-testid="share-link-role">
            <Select
              id={ids.role}
              value={role}
              onValueChange={(value) => {
                setRole(value as LinkRole);
              }}
              options={LINK_ROLES.map((r) => ({
                value: r,
                label:
                  roleRank(r) > roleRank(props.maxRole)
                    ? `${t(`roles.${r}`)} · ${t("form.roleCapped")}`
                    : t(`roles.${r}`),
                isDisabled: roleRank(r) > roleRank(props.maxRole),
              }))}
            />
          </div>
          {role === "editor" && (
            <Notice tone="warn" role="status" text={t("form.editorWarning")} />
          )}
        </div>
        {role === "reader" && (
          <SwitchRow
            label={t("form.sources")}
            hint={t("form.sourcesHint")}
            checked={sources}
            onChange={setSources}
            testId="share-link-sources"
          />
        )}
        <SwitchRow
          label={t("form.requireLogin")}
          hint={
            props.forcedLogin
              ? t("form.requireLoginForced")
              : t("form.requireLoginHint")
          }
          checked={requireLogin || props.forcedLogin}
          disabled={props.forcedLogin}
          onChange={setRequireLogin}
          testId="share-link-require-login"
        />
        <div className="share-link-field">
          <Input
            id={ids.password}
            type="password"
            autoComplete="new-password"
            label={t("form.password")}
            placeholder={
              link?.has_password
                ? t("form.passwordKeep")
                : t("form.passwordPlaceholder")
            }
            hint={t("form.passwordHint")}
            value={password}
            maxLength={PASSWORD_MAX}
            {...(passwordValid ? {} : { error: t("form.passwordHint") })}
            onChange={(event) => {
              setPassword(event.target.value);
              setClearPassword(false);
            }}
            data-testid="share-link-password"
          />
          {link?.has_password && (
            <label className="share-link-check">
              <input
                type="checkbox"
                checked={clearPassword}
                onChange={(event) => {
                  setClearPassword(event.target.checked);
                  if (event.target.checked) setPassword("");
                }}
                data-testid="share-link-clear-password"
              />
              {t("form.clearPassword")}
            </label>
          )}
        </div>
        <div className="share-link-field">
          <label htmlFor={ids.expiry}>{t("form.expiry")}</label>
          <div data-testid="share-link-expiry">
            <Select
              id={ids.expiry}
              value={expiry}
              onValueChange={setExpiry}
              options={expiryOptions}
            />
          </div>
          {editing && link.expires_at && expiry === KEEP && (
            <span className="share-link-muted">
              {t("row.until", { date: formatLinkDate(link.expires_at) })}
            </span>
          )}
        </div>
        {props.error && <Notice tone="err" role="alert" text={props.error} />}
      </form>
    </Modal>
  );
};

const SwitchRow = ({
  label,
  hint,
  checked,
  disabled,
  onChange,
  testId,
}: {
  label: string;
  hint: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
  testId: string;
}) => {
  const id = useId();
  return (
    <div className="share-link-switch">
      <div>
        <label htmlFor={id}>{label}</label>
        <p className="share-link-muted" id={`${id}-hint`}>
          {hint}
        </p>
      </div>
      <Switch
        id={id}
        checked={checked}
        onChange={onChange}
        disabled={disabled}
        describedBy={`${id}-hint`}
        testId={testId}
      />
    </div>
  );
};

/** После создания: адрес ссылки с копированием. */
export const CreatedLinkModal = ({
  url,
  onClose,
}: {
  url: string | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation("shareLinks");
  return (
    <Modal
      isOpen={url !== null}
      onClose={onClose}
      title={t("created.title")}
      description={t("created.description")}
      footer={
        <Button type="button" onClick={onClose}>
          {t("created.done")}
        </Button>
      }
    >
      {url && (
        <div data-testid="share-link-created-url" className="share-link-body">
          <CopyField value={url} label={t("row.url")} />
          <p className="share-link-muted">{t("created.hint")}</p>
        </div>
      )}
    </Modal>
  );
};

/** Подтверждение перевыпуска и отзыва. */
export const ConfirmLinkDialog = ({
  isOpen,
  title,
  body,
  confirmLabel,
  pending,
  onConfirm,
  onClose,
  testId,
}: {
  isOpen: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  pending?: boolean;
  onConfirm: () => void;
  onClose: () => void;
  testId: string;
}) => {
  const { t } = useTranslation("shareLinks");
  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (!pending) onClose();
      }}
      title={title}
      footer={
        <>
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={pending}
          >
            {t("form.cancel")}
          </Button>
          <Button
            type="button"
            variant="danger"
            onClick={onConfirm}
            disabled={pending}
            data-testid={`${testId}-confirm`}
          >
            {pending && <Spinner size="sm" />}
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p data-testid={testId}>{body}</p>
    </Modal>
  );
};

/** Переходы по ссылке (`share-link-visits`). */
export const LinkVisitsModal = ({
  link,
  status,
  items,
  onClose,
}: {
  link: ShareLink | null;
  status: "loading" | "error" | "ready";
  items: readonly ShareLinkVisit[];
  onClose: () => void;
}) => {
  const { t } = useTranslation("shareLinks");
  const when = (iso: string) =>
    `${formatLinkDate(iso)} ${new Date(iso).toLocaleTimeString(localeTag(), {
      hour: "2-digit",
      minute: "2-digit",
    })}`;
  return (
    <Modal
      isOpen={link !== null}
      onClose={onClose}
      title={link ? t("visits.title", { label: link.label }) : ""}
      width={560}
      footer={
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("visits.close")}
        </Button>
      }
    >
      <div data-testid="share-link-visits">
        {status === "loading" && <Spinner size="sm" />}
        {status === "ready" && items.length === 0 && (
          <p className="share-link-muted">{t("visits.empty")}</p>
        )}
        {status === "ready" && items.length > 0 && (
          <table className="share-link-visits-table">
            <thead>
              <tr>
                <th scope="col">{t("visits.who")}</th>
                <th scope="col">{t("visits.first")}</th>
                <th scope="col">{t("visits.last")}</th>
                <th scope="col">{t("visits.opens")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((visit, index) => (
                <tr key={`${visit.visitor_kind}-${String(index)}`}>
                  <td>
                    {visit.visitor_kind === "guest"
                      ? visit.name
                        ? t("visits.guest", { name: visit.name })
                        : t("visits.guestNoName")
                      : (visit.name ?? "")}
                  </td>
                  <td>{when(visit.first_at)}</td>
                  <td>{when(visit.last_at)}</td>
                  <td>{visit.opens}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Modal>
  );
};
