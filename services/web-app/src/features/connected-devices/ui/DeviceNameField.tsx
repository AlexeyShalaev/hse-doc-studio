import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "@shared/lib";
import { Button, Input } from "@shared/ui";
import type { LocalDevice } from "@entities/connected-device";

const MAX_NAME = 64;

export type DeviceNameFieldProps = {
  device: LocalDevice;
  busy?: boolean;
  onSave: (name: string | null) => void;
};

/**
 * Имя этого компьютера в облаке: по умолчанию имя машины, человек может назвать понятнее. После сохранения родитель
 * перерисовывает поле с новым ключом (`key={device.name}`), поэтому поле не копирует имя из props эффектом.
 */
export const DeviceNameField = ({
  device,
  busy = false,
  onSave,
}: DeviceNameFieldProps) => {
  const { t } = useTranslation("devices");
  const [value, setValue] = useState(device.name);
  const trimmed = value.trim();
  const tooLong = trimmed.length > MAX_NAME;
  const dirty = trimmed !== device.name && trimmed !== "";
  return (
    <div
      className="flex flex-col"
      style={{ gap: 6 }}
      data-testid="device-name-field"
    >
      <Input
        label={t("name.title")}
        value={value}
        placeholder={t("name.placeholder")}
        disabled={busy}
        {...(tooLong ? { error: t("name.tooLong") } : {})}
        onChange={(event) => {
          setValue(event.target.value);
        }}
        data-testid="device-name-input"
      />
      <span className="dim" style={{ fontSize: 11.5 }}>
        {t("name.hint")}
      </span>
      <div className="flex" style={{ gap: 8 }}>
        <Button
          variant="primary"
          size="sm"
          disabled={busy || !dirty || tooLong}
          onClick={() => {
            onSave(trimmed);
            toast.success(t("name.saved"));
          }}
          data-testid="device-name-save"
        >
          {t("name.save")}
        </Button>
        {device.custom && (
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => {
              onSave(null);
            }}
            data-testid="device-name-reset"
          >
            {t("name.reset", { name: device.default_name })}
          </Button>
        )}
      </div>
    </div>
  );
};
