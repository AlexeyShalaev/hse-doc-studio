import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useLocalDevice,
  useRenameDevice,
  useStudioLink,
} from "@entities/connected-device";
import { useBootstrap } from "@entities/session";
import { Section } from "@shared/ui";
import { pickServer } from "../model/summary";
import { DeviceNameField } from "./DeviceNameField";
import { LocalLinkPanel } from "./LocalLinkPanel";

/**
 * Раздел локальной Студии «Связь с облаком»: имя этого компьютера и то, как облако видит Студию сейчас. Рядом
 * с «Облачными сборками» в настройках; без входа на сервер показывается только имя.
 */
export const LocalLinkSection = () => {
  const { t } = useTranslation("devices");
  const mode = useBootstrap().data?.mode;
  const local = mode === "local";
  const device = useLocalDevice(local);
  const rename = useRenameDevice();
  const link = useStudioLink(null, local);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, 30_000);
    return () => {
      window.clearInterval(id);
    };
  }, []);
  if (!local || device.data === undefined) return null;
  const server = pickServer(link.data);
  return (
    <div
      id="studio-link"
      className="settings-anchor"
      data-testid="local-link-section"
    >
      <Section title={t("local.title")}>
        <DeviceNameField
          key={device.data.name}
          device={device.data}
          busy={rename.isPending}
          onSave={(name) => {
            rename.mutate(name);
          }}
        />
        {link.data !== undefined && server !== null && (
          <LocalLinkPanel link={link.data} now={now} embedded />
        )}
      </Section>
    </div>
  );
};
