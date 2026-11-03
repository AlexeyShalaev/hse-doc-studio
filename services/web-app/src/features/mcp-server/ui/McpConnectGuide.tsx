import { useTranslation } from "react-i18next";
import { CopyField, Section } from "@shared/ui";
import { clientConfigs } from "../lib/configs";

/** Адрес сервера и готовые конфиги клиентов; облаку с токеном в заголовке. */
export const McpConnectGuide = ({
  url,
  withToken,
}: {
  url: string;
  withToken: boolean;
}) => {
  const { t } = useTranslation("mcp");
  return (
    <Section
      title={t("connect.title")}
      description={withToken ? t("connect.hintServer") : t("connect.hintLocal")}
      testId="mcp-connect"
    >
      <div className="flex flex-col" style={{ gap: 12 }}>
        <CopyField value={url} label={t("connect.url")} />
        {clientConfigs(url, withToken).map((config) => (
          <div key={config.id} className="flex flex-col" style={{ gap: 4 }}>
            <strong style={{ fontSize: 13 }}>
              {t(`connect.clients.${config.id}`)}
            </strong>
            <CopyField
              value={config.text}
              label={t(`connect.clients.${config.id}`)}
              multiline
              wrap="spaces"
            />
          </div>
        ))}
      </div>
    </Section>
  );
};
