import { Cloud, CloudOff, Lock, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CollabSnapshot } from "../lib/collabProvider";

const MAX_AVATARS = 4;

const initials = (name: string): string =>
  name
    .replace(/^Гость:\s*/, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join("");

export type CollabBadgeProps = { snapshot: CollabSnapshot };

/** Состояние совместной правки: связь, режим чтения и кто сейчас в файле. */
export const CollabBadge = ({ snapshot }: CollabBadgeProps) => {
  const { t } = useTranslation("realtime");
  const { status, peers, canWrite, problem } = snapshot;
  const offline = status === "offline";
  const label = problem
    ? t(`problem.${problem}`, { defaultValue: problem })
    : t(`status.${status}`);
  const color =
    problem || offline
      ? "var(--c-warn)"
      : status === "connected"
        ? "var(--c-ok)"
        : "var(--fg-2)";
  const names = peers.map((p) => p.name).join(", ");
  return (
    <span
      className="flex items-center"
      style={{ gap: "0.375rem" }}
      data-testid="collab-badge"
      data-status={status}
    >
      <span
        className="tt"
        data-tt={label}
        role="status"
        aria-live="polite"
        style={{
          color,
          display: "inline-flex",
          alignItems: "center",
          gap: "0.1875rem",
          fontSize: "0.6875rem",
        }}
      >
        {offline ? <CloudOff size="0.75rem" /> : <Cloud size="0.75rem" />}
        <span>{t(`status.${offline ? "offline" : status}`).split(":")[0]}</span>
      </span>
      {!canWrite && status !== "refused" && (
        <span
          className="chip tt"
          data-tt={t("readOnly")}
          data-testid="collab-readonly"
        >
          <Lock size="0.625rem" />
        </span>
      )}
      {peers.length > 0 && (
        <span
          className="flex items-center tt"
          data-tt={t("peers", { names })}
          data-testid="collab-peers"
          style={{ gap: "0.125rem" }}
        >
          <Users size="0.75rem" style={{ color: "var(--fg-2)" }} />
          {peers.slice(0, MAX_AVATARS).map((peer) => (
            <span
              key={peer.clientId}
              aria-label={peer.name}
              style={{
                width: "1.125rem",
                height: "1.125rem",
                borderRadius: "0.5625rem",
                fontSize: "0.5625rem",
                fontWeight: 700,
                color: "#fff",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                background: peer.color,
                opacity: peer.writable ? 1 : 0.7,
              }}
            >
              {initials(peer.name)}
            </span>
          ))}
          {peers.length > MAX_AVATARS && (
            <span className="dim" style={{ fontSize: "0.65625rem" }}>
              +{peers.length - MAX_AVATARS}
            </span>
          )}
        </span>
      )}
    </span>
  );
};
