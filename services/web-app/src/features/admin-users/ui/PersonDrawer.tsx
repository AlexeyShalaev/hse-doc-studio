import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Avatar } from "@shared/ui";
import type { AdminUser } from "@entities/session";
import { formatFull } from "../lib/format";
import { ACTION_ICON, userActions, type UserActionKind } from "./userActions";
import { AccountStatusLabel, RoleLabel, When } from "./parts";

/** Карточка человека справа: сведения об аккаунте и все действия с пояснениями. */
export const PersonDrawer = ({
  user,
  self,
  busy,
  onClose,
  onAction,
}: {
  user: AdminUser | null;
  self: boolean;
  busy: boolean;
  onClose: () => void;
  onAction: (kind: UserActionKind) => void;
}) => {
  const { t, i18n } = useTranslation("adminUsers");
  const actions = user ? userActions(user, self) : [];
  const safe = actions.filter((a) => !a.danger);
  const danger = actions.filter((a) => a.danger);

  const renderAction = (a: (typeof actions)[number]) => (
    <button
      key={a.kind}
      type="button"
      className="ppl-drawer-action"
      data-danger={a.danger ? "true" : undefined}
      disabled={a.disabled || busy}
      data-testid={`drawer-${a.kind}`}
      onClick={() => {
        onAction(a.kind);
      }}
    >
      {ACTION_ICON[a.kind]}
      <span className="ppl-drawer-action-text">
        <span>{t(`users.actions.${a.kind}`)}</span>
        <span>
          {a.disabled
            ? t("users.actions.selfHint")
            : t(`drawer.hints.${a.kind}`)}
        </span>
      </span>
    </button>
  );

  return (
    <Dialog.Root
      open={user !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="ppl-drawer-scrim" />
        <Dialog.Content
          className="ppl-drawer"
          data-testid="person-drawer"
          aria-describedby={undefined}
        >
          {user && (
            <>
              <div className="ppl-drawer-head">
                <Avatar name={user.name} seed={user.id} size={44} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Dialog.Title className="ppl-drawer-title">
                    {user.name}
                    {self && (
                      <span className="ppl-muted" style={{ fontWeight: 400 }}>
                        {" "}
                        ({t("users.you")})
                      </span>
                    )}
                  </Dialog.Title>
                  <p className="ppl-drawer-sub">{user.email}</p>
                  <div className="ppl-drawer-badges">
                    <AccountStatusLabel status={user.status} />
                    <RoleLabel isAdmin={user.is_instance_admin} />
                  </div>
                </div>
                <Dialog.Close asChild>
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={t("close")}
                  >
                    <X size={16} aria-hidden="true" />
                  </button>
                </Dialog.Close>
              </div>
              <div className="ppl-drawer-body">
                <section>
                  <h3 className="ppl-drawer-caption">{t("drawer.account")}</h3>
                  <dl className="adm-kv">
                    <dt>{t("drawer.created")}</dt>
                    <dd title={formatFull(user.created_at, i18n.language)}>
                      <When iso={user.created_at} />
                    </dd>
                    <dt>{t("users.columns.lastLogin")}</dt>
                    <dd>
                      <When iso={user.last_login_at} empty={t("users.never")} />
                    </dd>
                    <dt>{t("users.columns.projects")}</dt>
                    <dd style={{ fontVariantNumeric: "tabular-nums" }}>
                      {user.project_count}
                    </dd>
                  </dl>
                </section>
                <section>
                  <h3 className="ppl-drawer-caption">{t("drawer.access")}</h3>
                  <div className="ppl-drawer-actions">
                    {safe.map(renderAction)}
                  </div>
                </section>
                <section>
                  <h3 className="ppl-drawer-caption">{t("drawer.danger")}</h3>
                  <div className="ppl-drawer-actions">
                    {danger.map(renderAction)}
                  </div>
                </section>
              </div>
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
