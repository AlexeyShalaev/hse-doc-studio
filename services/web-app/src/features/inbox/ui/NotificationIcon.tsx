import {
  ArrowRightLeft,
  AtSign,
  BellRing,
  CircleCheck,
  CirclePause,
  CircleX,
  DatabaseBackup,
  FileCheck,
  FilePen,
  HardDrive,
  KeyRound,
  MessageSquare,
  Reply,
  Undo2,
  TriangleAlert,
  UserCheck,
  UserMinus,
  UserPlus,
  UserX,
  type LucideIcon,
} from "lucide-react";
import type { NotificationKind } from "@entities/invitation";

const ICONS: Record<NotificationKind, LucideIcon> = {
  project_invitation: UserPlus,
  invitation_accepted: UserCheck,
  invitation_declined: UserX,
  access_request: KeyRound,
  access_request_decided: KeyRound,
  transfer_request: ArrowRightLeft,
  transfer_decided: ArrowRightLeft,
  member_removed: UserMinus,
  review_thread: MessageSquare,
  review_reply: Reply,
  review_mention: AtSign,
  review_resolved: CircleCheck,
  backup_failed: DatabaseBackup,
  system_alert: TriangleAlert,
  signing_request: FilePen,
  signing_reminder: BellRing,
  signing_returned: Undo2,
  signing_paused: CirclePause,
  signing_completed: FileCheck,
  signing_cancelled: CircleX,
  signing_new_version: FilePen,
  runner_disk_cleaned: HardDrive,
};

/** Значок типа уведомления; чисто декоративный, смысл несёт текст. */
export const NotificationIcon = ({
  kind,
  size = 15,
}: {
  kind: NotificationKind;
  size?: number;
}) => {
  const Icon = ICONS[kind];
  return <Icon size={size} aria-hidden="true" />;
};
