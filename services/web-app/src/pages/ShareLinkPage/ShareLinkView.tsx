import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { FileText, KeyRound, Link2Off, LogIn } from "lucide-react";
import type { ShareLinkPreview } from "@entities/share-link";
import { Button, Input, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

export type ShareLinkViewProps = {
  preview: ShareLinkPreview | null;
  status: "loading" | "ready" | "error";
  /** Имя вошедшего: «Вы войдёте как …». */
  signedInName?: string | null;
  /** Сервер попросил имя (после пароля у Редактора) или превью требует его. */
  needName?: boolean;
  pending?: boolean;
  /** Текст отказа под формой (неверный пароль, блокировка, прочее). */
  error?: string | null;
  onOpen: (input: {
    password: string | null;
    guestName: string | null;
  }) => void;
  loginHref: string;
};

const roleKey = (preview: ShareLinkPreview): string =>
  preview.role === "reader"
    ? preview.show_sources
      ? "readerSources"
      : "reader"
    : (preview.role ?? "reader");

/** Карточка страницы ссылки `/s/:token` во всех состояниях (10.3). Чистый вид без запросов. */
export const ShareLinkView = (props: ShareLinkViewProps) => {
  const { t } = useTranslation("guest");
  const ids = { name: useId(), password: useId() };
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const { preview } = props;
  const state =
    props.status === "error" ? "inactive" : (preview?.state ?? "loading");

  if (props.status === "loading" || !preview) {
    return (
      <section
        data-testid="share-link-page"
        data-state="loading"
        className="flex flex-col items-center"
        style={{ gap: 10, padding: "24px 0" }}
      >
        <Spinner />
        <span style={{ fontSize: 12.5, color: "var(--fg-2)" }}>
          {t("page.loading")}
        </span>
      </section>
    );
  }

  const heading = (
    <h1 style={{ fontSize: 20, fontWeight: 600, margin: "0 0 14px" }}>
      {t("page.title")}
    </h1>
  );
  const askName =
    !preview.signed_in &&
    (preview.guest_name_required || props.needName === true);
  const nameValid = !askName || name.trim().length > 0;

  if (state === "inactive") {
    return (
      <section data-testid="share-link-page" data-state="inactive">
        {heading}
        <div
          className="flex flex-col items-center"
          style={{ gap: 10, textAlign: "center", padding: "8px 0 4px" }}
        >
          <Link2Off
            size={28}
            aria-hidden="true"
            style={{ color: "var(--fg-2)" }}
          />
          <p
            style={{
              margin: 0,
              fontSize: 13,
              color: "var(--fg-1)",
              lineHeight: 1.5,
            }}
          >
            {t("page.inactive")}
          </p>
        </div>
        <div style={{ marginTop: 18 }}>
          <Button
            asChild
            variant="secondary"
            style={{ width: "100%", justifyContent: "center" }}
          >
            <Link to="/" style={{ textDecoration: "none" }}>
              {t("page.home")}
            </Link>
          </Button>
        </div>
      </section>
    );
  }

  if (state === "login_required" || state === "org_only") {
    return (
      <section data-testid="share-link-page" data-state={state}>
        {heading}
        {preview.project_name && <ProjectCard preview={preview} />}
        <p style={{ margin: "12px 0 0", fontSize: 13, lineHeight: 1.5 }}>
          {state === "org_only"
            ? t("page.orgOnly", { org: preview.owner_name ?? "" })
            : t("page.loginLead")}
        </p>
        <div style={{ marginTop: 18 }}>
          <Button asChild style={{ width: "100%", justifyContent: "center" }}>
            <Link
              to={props.loginHref}
              style={{ textDecoration: "none" }}
              data-testid="share-link-login"
            >
              <LogIn size={14} aria-hidden="true" /> {t("page.login")}
            </Link>
          </Button>
        </div>
      </section>
    );
  }

  const passwordStep = state === "password_required";
  return (
    <section data-testid="share-link-page" data-state={state}>
      {heading}
      <form
        className="flex flex-col"
        style={{ gap: 14 }}
        onSubmit={(event) => {
          event.preventDefault();
          if (!nameValid) return;
          props.onOpen({
            password: passwordStep ? password : null,
            guestName:
              askName || (!preview.signed_in && name.trim() !== "")
                ? name.trim()
                : null,
          });
        }}
      >
        {passwordStep ? (
          <p
            className="flex items-center"
            style={{ gap: 8, margin: 0, fontSize: 13 }}
          >
            <KeyRound size={15} aria-hidden="true" /> {t("page.passwordLead")}
          </p>
        ) : (
          <ProjectCard preview={preview} />
        )}
        {passwordStep && (
          <Input
            id={ids.password}
            type="password"
            autoComplete="off"
            label={t("page.password")}
            value={password}
            autoFocus
            onChange={(event) => {
              setPassword(event.target.value);
            }}
            data-testid="share-link-password-input"
          />
        )}
        {preview.signed_in && props.signedInName && (
          <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
            {t("page.signedInAs", { name: props.signedInName })}
          </p>
        )}
        {askName && (
          <Input
            id={ids.name}
            label={t("page.name")}
            hint={t("page.nameHint")}
            value={name}
            maxLength={64}
            autoFocus={!passwordStep}
            onChange={(event) => {
              setName(event.target.value);
            }}
            data-testid="share-link-guest-name"
          />
        )}
        {props.error && <Notice tone="err" role="alert" text={props.error} />}
        <Button
          type="submit"
          disabled={
            props.pending === true ||
            !nameValid ||
            (passwordStep && password === "")
          }
          style={{ width: "100%", justifyContent: "center" }}
          data-testid="share-link-open"
        >
          {props.pending && <Spinner size="sm" />}
          {t("page.open")}
        </Button>
      </form>
    </section>
  );
};

const ProjectCard = ({ preview }: { preview: ShareLinkPreview }) => {
  const { t } = useTranslation("guest");
  return (
    <div
      className="flex items-start"
      style={{
        gap: 12,
        padding: 14,
        border: "1px solid var(--border)",
        borderRadius: "var(--r-3)",
        background: "var(--bg-1)",
      }}
      data-testid="share-link-project"
    >
      <FileText
        size={20}
        aria-hidden="true"
        style={{ color: "var(--accent)", flexShrink: 0, marginTop: 2 }}
      />
      <div className="flex flex-col" style={{ gap: 4, minWidth: 0 }}>
        <strong style={{ fontSize: 13.5, lineHeight: 1.4 }}>
          {t("page.offered", {
            owner: preview.owner_name ?? "",
            project: preview.project_name ?? "",
          })}
        </strong>
        <span style={{ fontSize: 12, color: "var(--fg-2)" }}>
          {t(`page.role.${roleKey(preview)}`)}
        </span>
      </div>
    </div>
  );
};
