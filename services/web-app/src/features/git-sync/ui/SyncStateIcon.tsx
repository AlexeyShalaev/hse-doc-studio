import {
  CircleAlert,
  Cloud,
  CloudCheck,
  CloudDownload,
  CloudOff,
  CloudUpload,
  GitMerge,
  KeyRound,
  Lock,
  TriangleAlert,
  WifiOff,
  type LucideIcon,
} from "lucide-react";
import { Spinner } from "@shared/ui/Spinner";
import type { SyncIcon } from "../model/syncUi.model";

const ICONS: Record<Exclude<SyncIcon, "spinner">, LucideIcon> = {
  cloud_off: CloudOff,
  cloud: Cloud,
  cloud_check: CloudCheck,
  cloud_upload: CloudUpload,
  cloud_download: CloudDownload,
  git_merge: GitMerge,
  alert_triangle: TriangleAlert,
  key: KeyRound,
  wifi_off: WifiOff,
  alert_circle: CircleAlert,
  lock: Lock,
};

export type SyncStateIconProps = {
  icon: SyncIcon;
  size?: number;
};

export const SyncStateIcon = ({ icon, size = 15 }: SyncStateIconProps) => {
  if (icon === "spinner") {
    // Крутилка сама называет себя «Загрузка» для скринридера; здесь состояние
    // уже названо подписью кнопки, поэтому прячем дубль.
    return (
      <span aria-hidden="true" style={{ display: "inline-flex" }}>
        <Spinner size="sm" />
      </span>
    );
  }
  const Icon = ICONS[icon];
  return <Icon size={size} aria-hidden="true" />;
};
