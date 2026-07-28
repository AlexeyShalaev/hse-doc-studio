import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { HardDrive, X } from "lucide-react";
import { useCheckUpdate } from "@features/check-update";
import { useAppSettings } from "@entities/app-settings";
import { useDockerUsage } from "@entities/docker-system";
import { formatBytes, toast } from "@shared/lib";

const GIB = 1024 ** 3;

/**
 * Runs the two "on app open" checks: is a new version available, and has
 * Docker's disk footprint grown past the user's threshold (Settings → Диск).
 * Mounted once in RootLayout so it fires regardless of which route the user
 * lands on, and survives route navigation (RootLayout itself doesn't remount).
 *
 * Renders nothing for the update check (a one-shot toast); the disk warning
 * is a dismissible banner, since "go clean up Docker" needs a lasting CTA
 * rather than something that vanishes in 5 seconds.
 */
export const StartupChecks = () => {
  const { t } = useTranslation("appChrome");
  const navigate = useNavigate();

  const update = useCheckUpdate();
  const updateToastedRef = useRef(false);
  useEffect(() => {
    if (!update.updateAvailable || updateToastedRef.current) return;
    updateToastedRef.current = true;
    toast.info(
      t("startupChecks.updateAvailable", { version: update.latestVersion }),
      {
        title: t("startupChecks.updateAvailableTitle"),
        duration: 0,
        action: {
          label: t("startupChecks.updateAvailableAction"),
          onClick: () => {
            void navigate("/settings/about");
          },
        },
      },
    );
  }, [update.updateAvailable, update.latestVersion, navigate, t]);

  const { data: appSettings } = useAppSettings();
  const usage = useDockerUsage();
  const [diskBannerDismissed, setDiskBannerDismissed] = useState(false);

  const warnGb = appSettings?.disk_usage_warn_gb ?? 10;
  const cleanableBytes = usage.data?.cleanable_bytes ?? 0;
  const shouldWarnDisk =
    warnGb > 0 &&
    usage.data?.available === true &&
    cleanableBytes >= warnGb * GIB;

  if (!shouldWarnDisk || diskBannerDismissed) return null;

  return (
    <div
      role="status"
      style={{
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "7px 14px",
        background: "var(--c-warn-soft)",
        borderBottom: "1px solid var(--c-warn)",
        fontSize: 12,
      }}
    >
      <HardDrive size={13} style={{ color: "var(--c-warn)", flexShrink: 0 }} />
      <span style={{ color: "var(--c-warn)", fontWeight: 600, flexShrink: 0 }}>
        {t("diskBanner.title")}
      </span>
      <span className="dim" style={{ flex: 1, minWidth: 0 }}>
        {t("diskBanner.detail", { size: formatBytes(cleanableBytes) })}
      </span>
      <button
        type="button"
        className="btn xs"
        style={{ flexShrink: 0 }}
        onClick={() => {
          void navigate("/settings/disk");
        }}
      >
        {t("diskBanner.open")}
      </button>
      <button
        type="button"
        className="icon-btn"
        aria-label={t("diskBanner.dismiss")}
        style={{ flexShrink: 0 }}
        onClick={() => {
          setDiskBannerDismissed(true);
        }}
      >
        <X size={13} />
      </button>
    </div>
  );
};
