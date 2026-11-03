import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { i18n } from "@shared/lib";
import { ErrorState, Section, Spinner } from "@shared/ui";
import { useMcpInfo } from "../api/queries";
import { endpointUrl } from "../lib/configs";
import { McpConnectGuide } from "./McpConnectGuide";
import { McpSettingsPanel } from "./McpSettingsPanel";

const failureText = (error: unknown): string => {
  const key = `errors:code.${failureCode(error)}`;
  return i18n.exists(key) ? i18n.t(key) : i18n.t("mcp:failure.unknown");
};

/**
 * Раздел настроек «ИИ-клиенты (MCP)». Локальная Студия: включение, тулы,
 * журнал и конфиги без токена. Облако: адрес, конфиги с токеном и список
 * доступных тулов; включает MCP администратор.
 */
export const McpSection = () => {
  const { t } = useTranslation("mcp");
  const info = useMcpInfo();
  if (info.isPending) return <Spinner />;
  if (info.isError) {
    return (
      <ErrorState
        title={failureText(info.error)}
        onRetry={() => void info.refetch()}
      />
    );
  }
  const data = info.data;
  const url = endpointUrl(window.location.origin, data.endpoint_path);
  const server = data.mode === "server";
  return (
    <div
      className="flex flex-col"
      style={{ gap: 16 }}
      data-testid="mcp-section"
    >
      <div
        id="mcp"
        className="settings-anchor flex flex-col"
        style={{ gap: 4 }}
      >
        <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>
          {t("title")}
        </h4>
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: 12 }}>
          {t("lead")}
        </p>
      </div>
      {server && !data.enabled && (
        <p className="dim" data-testid="mcp-off">
          {t("serverOff")}
        </p>
      )}
      {(!server || data.enabled) && (
        <McpConnectGuide url={url} withToken={server} />
      )}
      {server && data.enabled && (
        <Section
          title={t("tools.available", { count: data.tools.length })}
          description={t("tools.tokenHint")}
        >
          <p style={{ margin: 0, lineHeight: 1.8 }}>
            {data.tools.map((name) => (
              <code key={name} style={{ marginRight: 8 }}>
                {name}
              </code>
            ))}
          </p>
        </Section>
      )}
      {!server && <McpSettingsPanel scope="local" />}
    </div>
  );
};
