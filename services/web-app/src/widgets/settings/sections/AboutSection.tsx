import { useState } from "react";
import { Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  OpenFolderInEditor,
  useSystemInfo,
  type SystemInfo,
} from "@entities/system";
import {
  ChangelogModal,
  useCheckUpdate,
  VersionSwitcher,
} from "@features/check-update";
import { useAppSettings, useUpdateAppSettings } from "@entities/app-settings";
import { i18n, toast } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { Setting, SettingHead } from "./Setting";

const MODE_LABELS: Record<SystemInfo["deployment_mode"], string> = {
  "all-in-one": "about.modeAllInOne",
  standard: "about.modeStandard",
  native: "about.modeNative",
};

const Logomark = () => (
  <div
    className="flex items-center justify-center font-mono shrink-0"
    style={{
      width: 22,
      height: 22,
      borderRadius: 5,
      background:
        "linear-gradient(135deg, var(--accent), color-mix(in oklch, var(--accent) 60%, var(--fg-0) 0%))",
      color: "var(--accent-ink)",
      fontWeight: 700,
      fontSize: 10,
      letterSpacing: "-0.02em",
      boxShadow: "0 0 0 1px var(--accent-line)",
    }}
  >
    §
  </div>
);

const Mono = ({ children }: { children: React.ReactNode }) => (
  <span className="mono" style={{ fontSize: 11.5 }}>
    {children}
  </span>
);

const copyPath = (value: string) => {
  navigator.clipboard
    .writeText(value)
    .then(() => {
      toast.info(i18n.t("settings:about.pathCopied"));
    })
    .catch(() => {
      toast.error(i18n.t("settings:about.copyFailed"));
    });
};

export const AboutSection = () => {
  const { t } = useTranslation("settings");
  const { data, isLoading } = useSystemInfo();
  const update = useCheckUpdate();
  const { data: appSettings } = useAppSettings();
  const updateAppSettings = useUpdateAppSettings();
  const [changelogOpen, setChangelogOpen] = useState(false);
  // Дефолт бэкенда — включено; пока настройки не приехали, показываем его же,
  // чтобы галочка не мигала из «выкл» в «вкл».
  const autoUpdate = appSettings?.auto_update ?? true;

  const sub = data
    ? t("about.license", { version: data.version, license: data.license })
    : undefined;
  const sourceLabel = data?.source_url.replace(/^https?:\/\//, "");

  return (
    <div className="flex flex-col" style={{ gap: 16 }}>
      <SettingHead
        anchorId="about"
        title="HSE Studio"
        {...(sub ? { sub } : {})}
      />
      <div
        className="flex flex-col"
        style={{
          gap: 8,
          padding: 14,
          background: "var(--bg-0)",
          borderRadius: "var(--r-3)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex items-center" style={{ gap: 8 }}>
          <Logomark />
          <strong>{t("about.productName")}</strong>
        </div>
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: 12 }}>
          {t("about.description")}
        </p>
      </div>

      <Setting anchorId="about-mode" label={t("about.runMode")}>
        {isLoading ? (
          <Spinner size="sm" />
        ) : (
          <span style={{ fontSize: 12 }}>
            {data ? t(MODE_LABELS[data.deployment_mode]) : "—"}
          </span>
        )}
      </Setting>

      <Setting anchorId="about-image" label={t("about.image")}>
        <Mono>{data?.image_ref ?? "—"}</Mono>
      </Setting>

      {/* Дату сборки знает только CI (build-arg в образе) — в исходной сборке её
          нет, и строку тогда не показываем вовсе. */}
      {data?.built && (
        <Setting anchorId="about-built" label={t("about.built")}>
          <Mono>{data.built}</Mono>
        </Setting>
      )}

      <Setting anchorId="about-source" label={t("about.source")}>
        {data ? (
          <a
            href={data.source_url}
            target="_blank"
            rel="noreferrer noopener"
            className="mono"
            style={{ fontSize: 11.5, color: "var(--accent)" }}
          >
            {sourceLabel}
          </a>
        ) : (
          <Mono>—</Mono>
        )}
      </Setting>

      {data?.data_dir && (
        <div id="about-data-dir" className="field settings-anchor">
          <label>{t("about.configFolder")}</label>
          <div className="flex gap-2">
            <input className="input mono" value={data.data_dir} readOnly />
            <button
              type="button"
              className="btn tt shrink-0"
              data-tt={t("about.copyPathTitle")}
              onClick={() => {
                copyPath(data.data_dir ?? "");
              }}
            >
              <Copy size={12} />
            </button>
            <OpenFolderInEditor path={data.data_dir} />
          </div>
          <span className="hint">{t("about.configFolderHint")}</span>
        </div>
      )}

      <Setting anchorId="about-updates" label={t("about.updates")}>
        {/* Проверку и её кэш держит бэкенд, поэтому здесь ровно три состояния:
            фид выключен, обновление есть, всё свежее. Пока /system/info не
            ответил, состояние фида неизвестно — иначе мигало бы «отключена». */}
        {isLoading ? (
          <Spinner size="sm" />
        ) : !update.feedEnabled ? (
          <span className="dim" style={{ fontSize: 12 }}>
            {t("about.updatesDisabled")}
          </span>
        ) : update.isChecking && !update.hasInfo ? (
          <Spinner size="sm" />
        ) : update.updateAvailable ? (
          <div className="flex items-center" style={{ gap: 8 }}>
            <span style={{ fontSize: 12, color: "var(--c-warn)" }}>
              {t("about.updateAvailable", { version: update.latestVersion })}
            </span>
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                setChangelogOpen(true);
              }}
            >
              {t("about.whatsNew")}
            </button>
          </div>
        ) : (
          <div className="flex items-center" style={{ gap: 8 }}>
            {update.hasInfo && (
              <span style={{ fontSize: 12, color: "var(--c-ok)" }}>
                {t("about.upToDate")}
              </span>
            )}
            <button
              type="button"
              className="btn xs"
              onClick={update.check}
              disabled={update.isChecking}
            >
              {update.hasInfo ? t("about.check") : t("about.checkUpdates")}
            </button>
            {update.reason && (
              <span className="dim" style={{ fontSize: 11 }}>
                {update.reason}
              </span>
            )}
          </div>
        )}
      </Setting>

      <Setting anchorId="about-auto-update" label={t("about.autoUpdate")}>
        <div className="flex flex-col" style={{ gap: 4 }}>
          <label
            className="flex items-center"
            style={{ gap: 6, fontSize: 12, cursor: "pointer" }}
          >
            <input
              type="checkbox"
              checked={autoUpdate}
              disabled={updateAppSettings.isPending}
              onChange={(e) => {
                updateAppSettings.mutate({ auto_update: e.target.checked });
              }}
            />
            {t("about.autoUpdateLabel")}
          </label>
          <span className="hint">
            {data?.can_self_update
              ? t("about.autoUpdateHint")
              : t("about.autoUpdateUnsupported")}
          </span>
        </div>
      </Setting>

      <Setting anchorId="about-version-switch" label={t("about.switchVersion")}>
        <VersionSwitcher
          canSelfUpdate={data?.can_self_update ?? false}
          enabled={data !== undefined}
        />
      </Setting>

      <ChangelogModal
        open={changelogOpen}
        onClose={() => {
          setChangelogOpen(false);
        }}
        release={update.latestRelease}
        version={update.latestVersion}
        deploymentMode={update.deploymentMode}
        canSelfUpdate={data?.can_self_update ?? false}
        sourceUrl={data?.source_url ?? null}
      />
    </div>
  );
};
