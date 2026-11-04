import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "@shared/lib";
import { Button, Modal, Section } from "@shared/ui";
import {
  DeviceCard,
  useAccountDevices,
  useForgetDevice,
  type Device,
} from "@entities/connected-device";
import { useBootstrap } from "@entities/session";
import { useAddCloudProvider } from "../model/useAddCloudProvider";

/** «Мои Студии» в облаке: локальные Студии, вошедшие в аккаунт, с их состоянием и кнопкой «Забыть устройство». */
export const AccountDevicesSection = () => {
  const { t } = useTranslation("devices");
  const mode = useBootstrap().data?.mode;
  const devices = useAccountDevices(mode === "server");
  const forget = useForgetDevice();
  const add = useAddCloudProvider();
  const [forgetting, setForgetting] = useState<Device | null>(null);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, 30_000);
    return () => {
      window.clearInterval(id);
    };
  }, []);
  if (mode !== "server") return null;
  const items = devices.data?.items ?? [];
  return (
    <div
      id="my-studios"
      className="settings-anchor"
      data-testid="account-devices"
    >
      <Section title={t("account.title")} description={t("account.lead")}>
        {items.length === 0 ? (
          <p className="dim" style={{ margin: 0, fontSize: 12 }}>
            {t("account.empty")}
          </p>
        ) : (
          <div className="flex flex-col" style={{ gap: 10 }}>
            {items.map((device) => (
              <DeviceCard
                key={device.id}
                device={device}
                now={now}
                showProject={false}
                adding={add.isPending && add.variables.device.id === device.id}
                onAddProvider={(endpoint) => {
                  add.mutate({ device, endpoint });
                }}
                actions={
                  <>
                    <span
                      className="dim"
                      style={{ fontSize: 11.5, alignSelf: "center" }}
                    >
                      {t("account.projects", { count: device.projects_count })}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      style={{ marginLeft: "auto", color: "var(--c-err)" }}
                      onClick={() => {
                        setForgetting(device);
                      }}
                      data-testid="device-forget"
                    >
                      {t("account.forget")}
                    </Button>
                  </>
                }
              />
            ))}
          </div>
        )}
      </Section>
      <Modal
        isOpen={forgetting !== null}
        title={t("account.forgetTitle", { name: forgetting?.name ?? "" })}
        description={t("account.forgetBody")}
        onClose={() => {
          setForgetting(null);
        }}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                setForgetting(null);
              }}
            >
              {t("account.cancel")}
            </Button>
            <Button
              variant="danger"
              disabled={forget.isPending}
              data-testid="device-forget-confirm"
              onClick={() => {
                if (forgetting === null) return;
                forget.mutate(forgetting.id, {
                  onSuccess: () => {
                    toast.success(t("account.forgotten"));
                    setForgetting(null);
                  },
                });
              }}
            >
              {t("account.forget")}
            </Button>
          </>
        }
      />
    </div>
  );
};
