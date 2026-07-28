import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { AlertTriangle, ExternalLink } from "lucide-react";
import { useDockerStatus } from "@entities/compile-images";

export const DockerStatusBanner = () => {
  const { t } = useTranslation("appChrome");
  const navigate = useNavigate();
  const { data, isLoading } = useDockerStatus();

  // While the first probe is in flight we deliberately render nothing —
  // a flashing "checking…" banner at the top of the app is more anxiety
  // than information. After the probe lands, only show if Docker is down.
  if (isLoading || !data || data.available) return null;

  // The backend hands us the raw daemon error (a long Windows named-pipe /
  // connect string). It's diagnostic, not actionable, so we keep it on a
  // single ellipsised line — full text on hover — rather than letting it
  // sprawl across and overlap the titlebar.
  const detail = data.detail ?? t("dockerBanner.defaultDetail");

  // Rendered in the normal flow at the very top of RootLayout's column, so it
  // pushes the titlebar down instead of floating over it (was position:fixed).
  return (
    <div
      role="alert"
      style={{
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "7px 14px",
        background: "var(--c-err-soft)",
        borderBottom: "1px solid var(--c-err)",
        fontSize: 12,
      }}
    >
      <AlertTriangle
        size={13}
        style={{ color: "var(--c-err)", flexShrink: 0 }}
      />
      <span style={{ color: "var(--c-err)", fontWeight: 600, flexShrink: 0 }}>
        {t("dockerBanner.unavailable")}
      </span>
      <span
        className="dim"
        title={detail}
        style={{
          flex: 1,
          minWidth: 0,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {detail}
      </span>
      <button
        type="button"
        className="btn xs"
        style={{ flexShrink: 0 }}
        onClick={() => {
          void navigate("/settings/compiler");
        }}
      >
        <ExternalLink size={11} />
        {t("dockerBanner.openSettings")}
      </button>
    </div>
  );
};
