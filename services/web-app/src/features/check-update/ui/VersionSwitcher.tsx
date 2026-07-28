import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppVersions, type VersionOption } from "@entities/system";
import { Spinner } from "@shared/ui/Spinner";
import { useSelfUpdate } from "../model/useSelfUpdate";

export type VersionSwitcherProps = {
  /** Умеет ли эта установка подменять себя (all-in-one + доступный Docker). */
  canSelfUpdate: boolean;
  enabled: boolean;
};

/**
 * Переключение на любую опубликованную версию — вперёд или назад.
 *
 * Список приходит из кэша последней проверки на бэкенде, поэтому открывается
 * мгновенно и работает офлайн. Откат — такое же законное действие, как
 * обновление: свежая версия может не подойти, и вернуться нужно без консоли.
 */
export const VersionSwitcher = ({
  canSelfUpdate,
  enabled,
}: VersionSwitcherProps) => {
  const { t } = useTranslation("checkUpdate");
  const { data, isLoading } = useAppVersions(enabled);
  const selfUpdate = useSelfUpdate();
  const [selected, setSelected] = useState<string | null>(null);

  if (isLoading) return <Spinner size="sm" />;

  const versions: VersionOption[] = data?.versions ?? [];
  const installed = data?.current ?? "";
  // Пока не выбрали явно — показываем установленную.
  const value = selected ?? installed;
  const target = versions.find((v) => v.version === value) ?? null;
  const isSwitch = target !== null && !target.installed;

  const label = (option: VersionOption): string =>
    [
      `v${option.version}`,
      option.installed ? `— ${t("versions.installed")}` : "",
      option.date ? `(${option.date})` : "",
    ]
      .filter(Boolean)
      .join(" ");

  return (
    <div className="flex flex-col" style={{ gap: 6 }}>
      <div className="flex items-center" style={{ gap: 8 }}>
        <select
          className="input"
          style={{ maxWidth: 260 }}
          value={value}
          disabled={selfUpdate.isBusy}
          onChange={(e) => {
            setSelected(e.target.value);
          }}
        >
          {versions.map((option) => (
            <option key={option.version} value={option.version}>
              {label(option)}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn xs"
          disabled={!isSwitch || !canSelfUpdate || selfUpdate.isBusy}
          onClick={() => {
            if (target) selfUpdate.start(target.version);
          }}
        >
          {selfUpdate.isBusy ? (
            <Spinner size="sm" />
          ) : target?.newer ? (
            t("versions.switchUp")
          ) : (
            t("versions.switchDown")
          )}
        </button>
      </div>

      {/* Ровно одна поясняющая строка — та, что относится к текущему состоянию. */}
      {selfUpdate.status === "failed" && selfUpdate.error ? (
        <span style={{ fontSize: 11, color: "var(--c-warn)" }}>
          {selfUpdate.error}
        </span>
      ) : selfUpdate.isBusy ? (
        <span className="dim" style={{ fontSize: 11 }}>
          {t("oneClick.busy")}
        </span>
      ) : !canSelfUpdate ? (
        <span className="dim" style={{ fontSize: 11 }}>
          {t("versions.manualOnly")}
        </span>
      ) : (
        isSwitch && (
          <span className="dim" style={{ fontSize: 11 }}>
            {target.newer ? t("versions.hintUp") : t("versions.hintDown")}
          </span>
        )
      )}
    </div>
  );
};
