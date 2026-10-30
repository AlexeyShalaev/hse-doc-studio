import type { ReactNode } from "react";
import {
  Ban,
  CircleCheck,
  KeyRound,
  LogOut,
  ShieldCheck,
  ShieldOff,
  Trash2,
} from "lucide-react";
import type { AdminUser } from "@entities/session";

export type UserActionKind =
  | "disable"
  | "enable"
  | "grantAdmin"
  | "revokeAdmin"
  | "remove"
  | "resetLink"
  | "revokeSessions";

/** Что можно сделать с аккаунтом и почему нельзя: общее для меню строки и карточки. */
export const userActions = (
  user: AdminUser,
  self: boolean,
): { kind: UserActionKind; disabled: boolean; danger: boolean }[] => [
  { kind: "resetLink", disabled: false, danger: false },
  { kind: "revokeSessions", disabled: false, danger: false },
  {
    kind: user.is_instance_admin ? "revokeAdmin" : "grantAdmin",
    disabled: self && user.is_instance_admin,
    danger: false,
  },
  user.status === "disabled"
    ? { kind: "enable", disabled: false, danger: false }
    : { kind: "disable", disabled: self, danger: true },
  ...(user.status === "disabled"
    ? [{ kind: "remove" as const, disabled: false, danger: true }]
    : []),
];

export const ACTION_ICON: Record<UserActionKind, ReactNode> = {
  resetLink: <KeyRound size={15} aria-hidden="true" />,
  revokeSessions: <LogOut size={15} aria-hidden="true" />,
  grantAdmin: <ShieldCheck size={15} aria-hidden="true" />,
  revokeAdmin: <ShieldOff size={15} aria-hidden="true" />,
  enable: <CircleCheck size={15} aria-hidden="true" />,
  disable: <Ban size={15} aria-hidden="true" />,
  remove: <Trash2 size={15} aria-hidden="true" />,
};
