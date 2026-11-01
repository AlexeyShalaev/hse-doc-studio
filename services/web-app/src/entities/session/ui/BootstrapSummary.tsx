import { useBootstrap } from "../api/sessionQueries";
import { ServerUnavailable } from "./ServerUnavailable";

// Что видит приложение после bootstrap: короткая сводка для живых записей галереи.
export const BootstrapSummary = () => {
  const { data, isLoading, isError } = useBootstrap();
  if (isLoading) return <p className="dim">...</p>;
  if (isError || !data) return <ServerUnavailable onRetry={() => undefined} />;
  const rows: [string, string][] = [
    ["mode", data.mode],
    ["setup_state", data.setup_state],
    ["registration_mode", data.auth.registration_mode],
    ["password_enabled", String(data.auth.password_enabled)],
    ["oidc", data.auth.oidc_providers.map((p) => p.label).join(", ") || "-"],
    ["user", data.user ? `${data.user.name} <${data.user.email}>` : "-"],
    ["admin", String(data.capabilities.admin)],
  ];
  return (
    <dl
      className="mono"
      style={{
        display: "grid",
        gridTemplateColumns: "max-content 1fr",
        gap: "4px 16px",
        margin: 0,
        fontSize: 12.5,
      }}
    >
      {rows.map(([key, value]) => (
        <div key={key} style={{ display: "contents" }}>
          <dt className="dim">{key}</dt>
          <dd style={{ margin: 0 }}>{value}</dd>
        </div>
      ))}
    </dl>
  );
};
