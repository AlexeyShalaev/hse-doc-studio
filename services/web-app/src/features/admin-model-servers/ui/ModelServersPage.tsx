import { useTranslation } from "react-i18next";
import { PageHeader, Section, Spinner } from "@shared/ui";
import { useCapabilities, useModelServers } from "../api/queries";
import { HardwarePanel } from "./HardwarePanel";
import { InstallPanel } from "./InstallPanel";
import { ServerCard } from "./ServerCard";

/** Админка: серверы ИИ-моделей (docs/design/model-servers.md). Только установка рядом со Студией. */
export const ModelServersPage = () => {
  const { t } = useTranslation("adminModelServers");
  const caps = useCapabilities();
  const servers = useModelServers();

  return (
    <>
      <PageHeader title={t("title")} description={t("lead")} />
      {caps.isPending && <Spinner />}
      {caps.data && !caps.data.local_enabled && (
        <Section testId="ms-disabled">
          <p style={{ margin: 0, padding: "0.75rem 1rem" }}>{t("disabled")}</p>
        </Section>
      )}
      {caps.data && caps.data.local_enabled && !caps.data.docker_available && (
        <Section testId="ms-no-docker">
          <p style={{ margin: 0, padding: "0.75rem 1rem" }}>{t("noDocker")}</p>
        </Section>
      )}
      {caps.data && <HardwarePanel caps={caps.data} />}
      {caps.data?.local_enabled && caps.data.docker_available && (
        <InstallPanel caps={caps.data} />
      )}
      <Section title={t("servers.title")} testId="ms-servers">
        {(servers.data ?? []).length === 0 ? (
          <p className="dim" style={{ margin: 0, padding: "0.75rem 1rem" }}>
            {t("servers.empty")}
          </p>
        ) : (
          <ul
            style={{
              listStyle: "none",
              margin: 0,
              padding: "0.75rem",
              display: "grid",
              gap: "0.75rem",
            }}
          >
            {(servers.data ?? []).map((s) => (
              <ServerCard key={s.id} server={s} />
            ))}
          </ul>
        )}
      </Section>
    </>
  );
};
