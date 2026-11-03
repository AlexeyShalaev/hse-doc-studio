import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { Button, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { AdminUserPasskey } from "@entities/session";
import { useResetPasskeys, useUserPasskeys } from "../api/adminUsersQueries";
import { When } from "./parts";

export type PersonPasskeysViewProps = {
  status: "loading" | "error" | "ready";
  items: AdminUserPasskey[];
  resetting: boolean;
  failed: boolean;
  onReset: () => void;
};

/** Passkey человека в карточке: сколько ключей, какие, и сброс всех разом. */
export const PersonPasskeysView = ({
  status,
  items,
  resetting,
  failed,
  onReset,
}: PersonPasskeysViewProps) => {
  const { t } = useTranslation("adminUsers");
  const [confirm, setConfirm] = useState(false);

  return (
    <div
      data-testid="person-passkeys"
      className="flex flex-col"
      style={{ gap: 8 }}
    >
      {status === "loading" && <Spinner size="sm" />}
      {status === "error" && (
        <Notice tone="err" role="alert" text={t("passkeys.loadFailed")} />
      )}
      {status === "ready" && (
        <>
          <p className="ppl-muted" style={{ margin: 0, fontSize: 12.5 }}>
            <span data-testid="person-passkeys-count">
              {t("passkeys.count", { count: items.length })}
            </span>
          </p>
          {items.length > 0 && (
            <ul
              style={{
                listStyle: "none",
                margin: 0,
                padding: 0,
                fontSize: 12.5,
              }}
              className="flex flex-col"
            >
              {items.map((item) => (
                <li
                  key={item.id}
                  data-testid={`person-passkey-${item.id}`}
                  style={{ padding: "4px 0" }}
                >
                  <span style={{ fontWeight: 500 }}>{item.name}</span>
                  <span className="ppl-muted">
                    {" · "}
                    {item.domain}
                    {" · "}
                    {t("passkeys.lastUsed")}{" "}
                    <When iso={item.last_used_at} empty={t("users.never")} />
                  </span>
                </li>
              ))}
            </ul>
          )}
          {failed && (
            <Notice tone="err" role="alert" text={t("passkeys.resetFailed")} />
          )}
          {items.length > 0 &&
            (confirm ? (
              <div className="flex flex-col" style={{ gap: 8 }}>
                <Notice tone="warn" text={t("passkeys.confirm")} />
                <div className="flex" style={{ gap: 8 }}>
                  <Button
                    type="button"
                    variant="danger"
                    size="sm"
                    data-testid="person-passkeys-reset-confirm"
                    aria-disabled={resetting}
                    onClick={() => {
                      if (resetting) return;
                      onReset();
                      setConfirm(false);
                    }}
                  >
                    {resetting && <Spinner size="sm" />}
                    {t("passkeys.reset")}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setConfirm(false);
                    }}
                  >
                    {t("passkeys.cancel")}
                  </Button>
                </div>
              </div>
            ) : (
              <div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  data-testid="person-passkeys-reset"
                  onClick={() => {
                    setConfirm(true);
                  }}
                >
                  {t("passkeys.reset")}
                </Button>
              </div>
            ))}
        </>
      )}
    </div>
  );
};

export const PersonPasskeys = ({ userId }: { userId: string }) => {
  const { t } = useTranslation("adminUsers");
  const list = useUserPasskeys(userId);
  const reset = useResetPasskeys();
  return (
    <PersonPasskeysView
      status={
        list.isError && !list.data ? "error" : list.data ? "ready" : "loading"
      }
      items={list.data ?? []}
      resetting={reset.isPending}
      failed={reset.isError && failureCode(reset.error) !== "not_found"}
      onReset={() => {
        reset.mutate(userId, {
          onSuccess: (removed) => {
            toast.success(t("passkeys.resetDone", { count: removed }));
          },
        });
      }}
    />
  );
};
