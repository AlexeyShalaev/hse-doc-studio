import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { useUpdateVcsSettings, useVcsSettings } from "@entities/vcs";

type ToggleRowProps = {
  label: string;
  hint: string;
  value: boolean;
  disabled?: boolean;
  onToggle: () => void;
};

const ToggleRow = ({
  label,
  hint,
  value,
  disabled,
  onToggle,
}: ToggleRowProps) => (
  <div
    className="flex items-center justify-between"
    style={{
      padding: 12,
      background: "var(--bg-2)",
      borderRadius: "var(--r-2)",
      gap: 12,
    }}
  >
    <div className="flex flex-col" style={{ gap: 1 }}>
      <strong style={{ fontSize: 12.5 }}>{label}</strong>
      <span className="dim" style={{ fontSize: 11 }}>
        {hint}
      </span>
    </div>
    <span
      className={clsx("toggle", value && "on", disabled && "disabled")}
      onClick={disabled ? undefined : onToggle}
    />
  </div>
);

export type VcsSettingsCardProps = {
  projectId: string;
};

export const VcsSettingsCard = ({ projectId }: VcsSettingsCardProps) => {
  const { t } = useTranslation("vcsHistory");
  const { data: settings } = useVcsSettings(projectId);
  const { mutate, isPending } = useUpdateVcsSettings();

  if (!settings) return null;

  const patch = (params: Parameters<typeof mutate>[0]["params"]) => {
    mutate({ projectId, params });
  };

  return (
    <div className="flex flex-col" style={{ gap: 10 }}>
      <ToggleRow
        label={t("settings.trackingLabel")}
        hint={t("settings.trackingHint")}
        value={settings.tracking_enabled}
        disabled={isPending}
        onToggle={() => {
          patch({ tracking_enabled: !settings.tracking_enabled });
        }}
      />
      <ToggleRow
        label={t("settings.pdfLabel")}
        hint={t("settings.pdfHint")}
        value={settings.track_pdf}
        disabled={isPending}
        onToggle={() => {
          patch({ track_pdf: !settings.track_pdf });
        }}
      />
    </div>
  );
};
