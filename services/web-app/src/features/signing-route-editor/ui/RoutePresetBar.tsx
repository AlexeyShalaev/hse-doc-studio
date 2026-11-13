import { useState } from "react";
import { useTranslation } from "react-i18next";
import { LayoutTemplate, PencilLine, RotateCcw } from "lucide-react";
import type { RoutePreset } from "@entities/signing-route";
import { Modal, Spinner } from "@shared/ui";

export type RoutePresetBarProps = {
  preset: RoutePreset;
  /** Идёт «Вернуть как в шаблоне» или другая правка маршрута. */
  busy: boolean;
  pending: boolean;
  /** «Вернуть» в окне подтверждения; окно закрывается, когда запрос завершится. */
  onRestore: () => Promise<unknown>;
};

/**
 * Шапка редактора маршрута (docs/design/signing-route.md, 15.7): «Маршрут из шаблона», если
 * порядок, подписи сверх точки и отметки «необязательна» как в шаблоне; иначе «Изменён вами» и
 * «Вернуть как в шаблоне» с подтверждением. Если состав собран по пресету прежней версии шаблона
 * (`base_version` не равна `version`), а пресет новой версии другой, вместо «Изменён вами» строка
 * «В новой версии шаблона другой маршрут этой точки» и та же кнопка. Места подписей на страницах
 * кнопка не трогает.
 */
export const RoutePresetBar = ({
  preset,
  busy,
  pending,
  onRestore,
}: RoutePresetBarProps) => {
  const { t } = useTranslation("signingRouteEditor");
  const [asking, setAsking] = useState(false);
  const changed = preset.differs.length > 0;
  // Состав собран по пресету другой версии (обычно до обновления шаблона), а пресет новой версии
  // другой: это не правка автора, а новый маршрут шаблона (15.7, `base_version`).
  const newVersion = changed && preset.base_version !== preset.version;
  const what = preset.differs
    .map((diff) => t(`preset.diff.${diff}`))
    .join(", ");
  return (
    <div
      className="flex items-center"
      style={{
        gap: "0.5rem",
        flexWrap: "wrap",
        marginTop: "0.75rem",
        fontSize: "0.75rem",
      }}
      data-testid="route-preset"
      data-differs={preset.differs.join(" ")}
      data-new-version={newVersion ? "" : undefined}
    >
      <span
        className={changed ? "chip subtle" : "chip accent"}
        title={
          newVersion
            ? t("preset.newVersionTitle", { version: preset.version, what })
            : changed
              ? t("preset.changedTitle", { what })
              : t("preset.fromTemplateTitle", { version: preset.version })
        }
        data-testid="route-preset-mark"
      >
        {changed && !newVersion ? (
          <PencilLine size="0.6875rem" aria-hidden="true" />
        ) : (
          <LayoutTemplate size="0.6875rem" aria-hidden="true" />
        )}
        {newVersion
          ? t("preset.newVersion")
          : changed
            ? t("preset.changed")
            : t("preset.fromTemplate")}
      </span>
      {changed && (
        <>
          <span className="dim">{t("preset.changedWhat", { what })}</span>
          <button
            type="button"
            className="btn xs"
            disabled={busy}
            data-testid="route-preset-reset"
            onClick={() => {
              setAsking(true);
            }}
          >
            <RotateCcw size="0.6875rem" aria-hidden="true" />
            {t("preset.reset")}
          </button>
        </>
      )}
      <RestorePresetDialog
        isOpen={asking}
        pending={pending}
        onCancel={() => {
          setAsking(false);
        }}
        onConfirm={() => {
          void onRestore().finally(() => {
            setAsking(false);
          });
        }}
      />
    </div>
  );
};

export type RestorePresetDialogProps = {
  isOpen: boolean;
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

/** «Вернуть как в шаблоне?» (15.7): что вернётся и что останется как есть. */
export const RestorePresetDialog = ({
  isOpen,
  pending,
  onConfirm,
  onCancel,
}: RestorePresetDialogProps) => {
  const { t } = useTranslation("signingRouteEditor");
  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (!pending) onCancel();
      }}
      title={t("preset.confirm.title")}
      footer={
        <>
          <button
            type="button"
            className="btn"
            disabled={pending}
            onClick={onCancel}
          >
            {t("preset.confirm.cancel")}
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={pending}
            data-testid="route-preset-confirm"
            onClick={onConfirm}
          >
            {pending && <Spinner size="sm" />}
            {t("preset.confirm.reset")}
          </button>
        </>
      }
    >
      <p
        style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.5 }}
        data-testid="route-preset-confirm-text"
      >
        {t("preset.confirm.text")}
      </p>
    </Modal>
  );
};
