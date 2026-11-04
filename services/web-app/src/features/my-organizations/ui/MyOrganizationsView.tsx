import { useState } from "react";
import { Building2, LogOut, Settings2, Users } from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { Badge, Button, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { MyOrg, OrgRoleName } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";

export type MyOrganizationsViewProps = {
  status: "loading" | "error" | "ready";
  orgs?: MyOrg[];
  /** Отказ выхода (показывается над списком). */
  failure?: Failure | null;
  /** Организация, из которой выходят прямо сейчас. */
  leavingSlug?: string | null;
  /** Админ установки управляет любой организацией. */
  instanceAdmin?: boolean;
  onRetry?: () => void;
  onLeave: (org: MyOrg) => void;
  /** Сбросить отказ при новом действии. */
  onReset?: () => void;
};

const ROLE_VARIANT = {
  owner: "accent",
  admin: "info",
  member: "subtle",
} as const satisfies Record<OrgRoleName, string>;

const manages = (org: MyOrg, instanceAdmin: boolean): boolean =>
  instanceAdmin || org.my_role === "owner" || org.my_role === "admin";

/** Раздел «Организации» в настройках: карточки с ролью и группами, выход с подтверждением. */
export const MyOrganizationsView = ({
  status,
  orgs = [],
  failure = null,
  leavingSlug = null,
  instanceAdmin = false,
  onRetry,
  onLeave,
  onReset,
}: MyOrganizationsViewProps) => {
  const { t } = useTranslation("organizations");
  const [confirming, setConfirming] = useState<MyOrg | null>(null);

  return (
    <>
      <div
        id="organizations"
        className="flex flex-col settings-anchor"
        style={{ gap: "0.25rem", marginBottom: "0.25rem" }}
      >
        <h4 style={{ margin: 0, fontSize: "0.875rem", fontWeight: 600 }}>
          {t("section.title")}
        </h4>
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: "0.75rem" }}>
          {t("section.subtitle")}
        </p>
      </div>

      <div
        className="flex flex-col"
        style={{
          gap: "0.875rem",
          paddingBottom: "0.875rem",
          maxWidth: "35rem",
        }}
        data-testid="my-orgs"
      >
        {status === "loading" && (
          <div
            className="flex items-center"
            style={{ gap: "0.5rem", fontSize: "0.75rem" }}
            data-testid="my-orgs-loading"
          >
            <Spinner size="sm" />
            <span className="dim">{t("section.loading")}</span>
          </div>
        )}

        {status === "error" && (
          <Notice
            tone="err"
            role="alert"
            text={t("section.loadFailed")}
            action={
              onRetry && (
                <button type="button" className="btn xs" onClick={onRetry}>
                  {t("section.retry")}
                </button>
              )
            }
          />
        )}

        {failure && (
          <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
        )}

        {status === "ready" && orgs.length === 0 && (
          <div
            data-testid="my-orgs-empty"
            className="flex flex-col items-center"
            style={{
              gap: "0.5rem",
              padding: "2rem 1.25rem",
              textAlign: "center",
              border: "1px dashed var(--border)",
              borderRadius: "var(--r-3)",
              background: "var(--bg-1)",
            }}
          >
            <Building2
              size="1.625rem"
              aria-hidden="true"
              style={{ color: "var(--fg-2)" }}
            />
            <strong style={{ fontSize: "0.84375rem" }}>
              {t("empty.title")}
            </strong>
            <p
              style={{
                margin: 0,
                fontSize: "0.75rem",
                color: "var(--fg-2)",
                maxWidth: "23.75rem",
                lineHeight: 1.5,
              }}
            >
              {t("empty.description")}
            </p>
          </div>
        )}

        {status === "ready" &&
          orgs.map((org) => {
            const leaving = leavingSlug === org.slug;
            return (
              <section
                key={org.slug}
                data-testid={`my-org-${org.slug}`}
                style={{
                  padding: "1rem",
                  borderRadius: "var(--r-3)",
                  border: "1px solid var(--border)",
                  background: "var(--bg-1)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.75rem",
                }}
              >
                <div className="flex items-start" style={{ gap: "0.75rem" }}>
                  <div
                    className="flex flex-col"
                    style={{ gap: "0.1875rem", flex: 1, minWidth: 0 }}
                  >
                    <h5
                      style={{
                        margin: 0,
                        fontSize: "0.84375rem",
                        fontWeight: 600,
                        overflowWrap: "anywhere",
                      }}
                    >
                      {org.name}
                    </h5>
                    <span
                      className="flex items-center"
                      style={{
                        gap: "0.375rem",
                        fontSize: "0.71875rem",
                        color: "var(--fg-2)",
                      }}
                    >
                      <Users size="0.75rem" aria-hidden="true" />
                      {t("card.members", { count: org.member_count })}
                    </span>
                  </div>
                  <Badge
                    variant={ROLE_VARIANT[org.my_role]}
                    data-testid={`my-org-role-${org.slug}`}
                  >
                    {t(`role.${org.my_role}`)}
                  </Badge>
                </div>

                <p
                  style={{
                    margin: 0,
                    fontSize: "0.75rem",
                    color: "var(--fg-2)",
                    lineHeight: 1.5,
                  }}
                >
                  {t(`roleHint.${org.my_role}`)}
                </p>

                <div className="flex flex-col" style={{ gap: "0.375rem" }}>
                  <span
                    style={{
                      fontSize: "0.71875rem",
                      color: "var(--fg-2)",
                      fontWeight: 500,
                    }}
                  >
                    {t("card.groups")}
                  </span>
                  {org.groups.length === 0 ? (
                    <span style={{ fontSize: "0.75rem", color: "var(--fg-2)" }}>
                      {t("card.noGroups")}
                    </span>
                  ) : (
                    <div
                      className="flex"
                      style={{ gap: "0.375rem", flexWrap: "wrap" }}
                    >
                      {org.groups.map((g) => (
                        <Badge key={g} variant="subtle">
                          {g}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>

                {org.sole_owner && (
                  <Notice tone="warn" text={t("card.soleOwner")} />
                )}

                <div
                  className="flex items-center"
                  style={{ gap: "0.5rem", flexWrap: "wrap" }}
                >
                  {manages(org, instanceAdmin) && (
                    <Link
                      to={`/admin/orgs/${encodeURIComponent(org.slug)}`}
                      className="btn sm"
                      data-testid={`my-org-manage-${org.slug}`}
                      style={{ gap: "0.375rem" }}
                    >
                      <Settings2 size="0.875rem" aria-hidden="true" />
                      {t("card.manage")}
                    </Link>
                  )}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={org.sole_owner || leaving}
                    data-testid={`my-org-leave-${org.slug}`}
                    style={{ gap: "0.375rem" }}
                    onClick={() => {
                      onReset?.();
                      setConfirming(org);
                    }}
                  >
                    {leaving ? (
                      <Spinner size="sm" />
                    ) : (
                      <LogOut size="0.875rem" aria-hidden="true" />
                    )}
                    {t("card.leave")}
                  </Button>
                </div>
              </section>
            );
          })}
      </div>

      <Modal
        isOpen={confirming !== null}
        onClose={() => {
          setConfirming(null);
        }}
        title={t("leave.title", { name: confirming?.name ?? "" })}
        description={t("leave.description")}
        footer={
          <>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setConfirming(null);
              }}
            >
              {t("leave.cancel")}
            </Button>
            <Button
              type="button"
              variant="danger"
              data-testid="my-org-leave-confirm"
              onClick={() => {
                if (confirming) onLeave(confirming);
                setConfirming(null);
              }}
            >
              {t("leave.confirm")}
            </Button>
          </>
        }
      />
    </>
  );
};
