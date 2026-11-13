import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { CopyField, Section, Select } from "@shared/ui";
import { CLIENT_IDS, TOKEN_ENV, clientConfigs } from "../lib/configs";
import type { ClientId } from "../lib/configs";

/**
 * Адрес сервера и готовый конфиг выбранного клиента; облаку с токеном.
 * Клиентов много, поэтому на экране один конфиг: список не растягивает
 * страницу и помещается на телефоне.
 */
export const McpConnectGuide = ({
  url,
  withToken,
}: {
  url: string;
  withToken: boolean;
}) => {
  const { t } = useTranslation("mcp");
  const uid = useId();
  const [client, setClient] = useState<ClientId>("claudeCode");
  const configs = clientConfigs(url, withToken);
  const config = configs.find((c) => c.id === client) ?? configs[0];
  if (!config) return null;
  const name = t(`connect.clients.${config.id}`);
  return (
    <Section
      title={t("connect.title")}
      description={withToken ? t("connect.hintServer") : t("connect.hintLocal")}
      testId="mcp-connect"
    >
      <div className="flex flex-col" style={{ gap: "0.75rem" }}>
        <CopyField value={url} label={t("connect.url")} />
        <div className="flex flex-col" style={{ gap: "0.25rem" }}>
          <label
            htmlFor={`${uid}-client`}
            style={{ fontSize: "0.8125rem", fontWeight: 600 }}
          >
            {t("connect.client")}
          </label>
          <Select
            id={`${uid}-client`}
            ariaLabel={t("connect.client")}
            value={client}
            onValueChange={(value) => {
              setClient(value as ClientId);
            }}
            options={CLIENT_IDS.map((id) => ({
              value: id,
              label: t(`connect.clients.${id}`),
            }))}
          />
        </div>
        <CopyField value={config.text} label={name} multiline wrap="spaces" />
        <p
          className="dim"
          style={{ margin: 0, fontSize: "0.75rem" }}
          data-testid="mcp-connect-note"
        >
          {t(`connect.where.${config.id}`)}
          {config.tokenFromEnv &&
            ` ${t("connect.tokenEnv", { env: TOKEN_ENV })}`}{" "}
          <a href={config.docs} target="_blank" rel="noreferrer">
            {t("connect.docs")}
          </a>
        </p>
      </div>
    </Section>
  );
};
