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
      style={{ gap: 6 }}
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
          gap: 3,
          fontSize: 11,
        }}
      >
        {offline ? <CloudOff size={12} /> : <Cloud size={12} />}
        <span>{t(`status.${offline ? "offline" : status}`).split(":")[0]}</span>
      </span>
      {!canWrite && status !== "refused" && (
        <span
          className="chip tt"
          data-tt={t("readOnly")}
          data-testid="collab-readonly"
        >
          <Lock size={10} />
        </span>
      )}
      {peers.length > 0 && (
        <span
          className="flex items-center tt"
          data-tt={t("peers", { names })}
          data-testid="collab-peers"
          style={{ gap: 2 }}
        >
          <Users size={12} style={{ color: "var(--fg-2)" }} />
          {peers.slice(0, MAX_AVATARS).map((peer) => (
            <span
              key={peer.clientId}
              aria-label={peer.name}
              style={{
                width: 18,
                height: 18,
                borderRadius: 9,
                fontSize: 9,
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
            <span className="dim" style={{ fontSize: 10.5 }}>
              +{peers.length - MAX_AVATARS}
            </span>
          )}
        </span>
      )}
    </span>
  );
};
