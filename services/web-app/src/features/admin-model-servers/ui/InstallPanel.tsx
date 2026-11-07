import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Badge, Button, Input, Section, Select, SettingRow } from "@shared/ui";
import { SshInstallDialog } from "@features/admin-ops";
import { useCatalog, useEstimate, useInstall } from "../api/queries";
import type { Capabilities, Engine } from "../api/schemas";
import { gbOf } from "../lib/format";

const FIT_VARIANT = {
  fits: "success",
  tight: "warning",
  too_large: "error",
  unknown: "default",
} as const;

/** Выбор движка и модели, оценка требований до скачивания и запуск установки. */
export const InstallPanel = ({ caps }: { caps: Capabilities }) => {
  const { t } = useTranslation("adminModelServers");
  const [engine, setEngine] = useState<Engine>("ollama");
  const [model, setModel] = useState("");
  const [name, setName] = useState("");
  const [force, setForce] = useState(false);
  const [where, setWhere] = useState<"local" | "ssh">(
    caps.local_enabled && caps.docker_available ? "local" : "ssh",
  );
  const [exposure, setExposure] = useState<"localhost" | "public">("localhost");
  const [ackPublic, setAckPublic] = useState(false);
  const [sshOpen, setSshOpen] = useState(false);
  const catalog = useCatalog(engine, "");
  const estimate = useEstimate(engine, model.trim());
  const install = useInstall();
  const availability = caps.engines.find((e) => e.engine === engine);
  const est = estimate.data;
  // Видеокарту и память удалённой машины проверяет сервер при установке по SSH, подсказки железа относятся к локальной.
  const blocked =
    where === "local" &&
    ((availability ? !availability.available : false) ||
      est?.fit === "too_large");
  const canForce = blocked;
  const publicBlocked =
    where === "ssh" &&
    exposure === "public" &&
    (engine === "ollama" || !ackPublic);
  const disabled =
    model.trim() === "" ||
    install.isPending ||
    (blocked && !force) ||
    publicBlocked;
  const localReady = caps.local_enabled && caps.docker_available;
  const error = install.isError ? failureCode(install.error) : null;
  const gb = (mb: number | null) =>
    t("hardware.gb", { value: gbOf(mb) ?? "?" });

  return (
    <>
      <Section
        title={t("install.title")}
        description={t("install.lead")}
        testId="ms-install"
        footer={
          <div
            className="flex flex-wrap items-center"
            style={{ gap: "0.75rem" }}
          >
            <Button
              disabled={disabled}
              data-testid="ms-install-submit"
              onClick={() => {
                if (where === "ssh") {
                  setSshOpen(true);
                  return;
                }
                install.mutate(
                  { engine, model: model.trim(), name: name.trim(), force },
                  {
                    onSuccess: () => {
                      setModel("");
                      setName("");
                      setForce(false);
                    },
                  },
                );
              }}
            >
              {where === "ssh" ? t("install.submitSsh") : t("install.submit")}
            </Button>
            {error && (
              <span
                className="form-hint"
                role="alert"
                data-testid="ms-install-error"
              >
                {t(`error.${error}`, { defaultValue: t("error.generic") })}
              </span>
            )}
          </div>
        }
      >
        <SettingRow label={t("install.where")} htmlFor="ms-where">
          <Select
            id="ms-where"
            value={where}
            onValueChange={(v) => {
              setWhere(v as "local" | "ssh");
            }}
            options={[
              {
                value: "local",
                label: t("install.whereLocal"),
                isDisabled: !localReady,
              },
              { value: "ssh", label: t("install.whereSsh") },
            ]}
            ariaLabel={t("install.where")}
          />
        </SettingRow>
        <SettingRow label={t("install.engine")} htmlFor="ms-engine">
          <Select
            id="ms-engine"
            value={engine}
            onValueChange={(v) => {
              setEngine(v as Engine);
              setModel("");
            }}
            options={caps.engines.map((e) => ({
              value: e.engine,
              label: t(`engine.${e.engine}`),
            }))}
            ariaLabel={t("install.engine")}
          />
        </SettingRow>
        <SettingRow
          label={t("install.model")}
          hint={t(`install.modelHint.${engine}`)}
          htmlFor="ms-model"
        >
          <Input
            id="ms-model"
            value={model}
            list="ms-catalog"
            autoComplete="off"
            onChange={(e) => {
              setModel(e.target.value);
            }}
            data-testid="ms-model"
          />
          <datalist id="ms-catalog">
            {(catalog.data ?? []).map((m) => (
              <option key={m.ref} value={m.ref}>
                {m.title}
              </option>
            ))}
          </datalist>
        </SettingRow>
        <SettingRow
          label={t("install.name")}
          hint={t("install.nameHint")}
          htmlFor="ms-name"
        >
          <Input
            id="ms-name"
            value={name}
            maxLength={64}
            onChange={(e) => {
              setName(e.target.value);
            }}
          />
        </SettingRow>
        {where === "ssh" && (
          <>
            <SettingRow
              label={t("install.exposure")}
              hint={t("install.exposureHint")}
              htmlFor="ms-exposure"
            >
              <Select
                id="ms-exposure"
                value={exposure}
                onValueChange={(v) => {
                  setExposure(v as "localhost" | "public");
                  setAckPublic(false);
                }}
                options={[
                  { value: "localhost", label: t("install.exposureLocalhost") },
                  {
                    value: "public",
                    label: t("install.exposurePublic"),
                    isDisabled: engine === "ollama",
                  },
                ]}
                ariaLabel={t("install.exposure")}
              />
            </SettingRow>
            {exposure === "public" && (
              <label
                className="flex items-center"
                style={{
                  gap: "0.5rem",
                  padding: "0 1rem 0.75rem",
                  fontSize: "0.875rem",
                }}
              >
                <input
                  type="checkbox"
                  checked={ackPublic}
                  data-testid="ms-ack-public"
                  onChange={(e) => {
                    setAckPublic(e.target.checked);
                  }}
                />
                {t("install.ackPublic")}
              </label>
            )}
          </>
        )}
        {est && model.trim() !== "" && (
          <div style={{ padding: "0.75rem 1rem" }} data-testid="ms-estimate">
            <Badge variant={FIT_VARIANT[est.fit]}>{t(`fit.${est.fit}`)}</Badge>
            {est.weights_mb !== null && est.needed_mb !== null && (
              <p style={{ margin: "0.5rem 0 0", fontSize: "0.875rem" }}>
                {t("estimate.summary", {
                  weights: gb(est.weights_mb),
                  needed: gb(est.needed_mb),
                  available: gb(est.available_mb),
                  kind: t(`estimate.${est.memory_kind}`),
                })}
              </p>
            )}
            {est.reasons.length > 0 && (
              <ul
                style={{
                  margin: "0.5rem 0 0",
                  paddingLeft: "1.25rem",
                  fontSize: "0.875rem",
                }}
              >
                {est.reasons.map((r) => (
                  <li key={r}>{t(`reason.${r}`, { defaultValue: r })}</li>
                ))}
              </ul>
            )}
            <p
              className="dim"
              style={{ margin: "0.5rem 0 0", fontSize: "0.75rem" }}
            >
              {t("estimate.rough")}
            </p>
          </div>
        )}
        {canForce && (
          <label
            className="flex items-center"
            style={{
              gap: "0.5rem",
              padding: "0 1rem 0.75rem",
              fontSize: "0.875rem",
            }}
          >
            <input
              type="checkbox"
              checked={force}
              data-testid="ms-force"
              onChange={(e) => {
                setForce(e.target.checked);
              }}
            />
            {t("install.force")}
          </label>
        )}
      </Section>
      <SshInstallDialog
        isOpen={sshOpen}
        onClose={() => {
          setSshOpen(false);
        }}
        modelServer={{
          engine,
          model: model.trim(),
          name: name.trim(),
          exposure,
          acknowledge_public: ackPublic,
          force,
        }}
      />
    </>
  );
};
