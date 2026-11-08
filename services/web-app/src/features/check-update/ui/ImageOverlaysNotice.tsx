import { useTranslation } from "react-i18next";
import type { ImageOverlay } from "@entities/system";

const PACKS_DIR = "/app/packs";

export type ImageOverlaysNoticeProps = {
  overlays: ImageOverlay[];
};

/**
 * Что станет при обновлении с папками хоста, привязанными поверх каталогов
 * образа. Подключённый каталог шаблонов после обновления остаётся прежним и
 * отстаёт от новой версии: проекты на свежих версиях шаблона откроются только
 * для чтения. Человек должен знать это до нажатия кнопки, а не после.
 */
export const ImageOverlaysNotice = ({ overlays }: ImageOverlaysNoticeProps) => {
  const { t } = useTranslation("checkUpdate");
  if (overlays.length === 0) return null;
  return (
    <div className="flex flex-col" style={{ gap: "0.25rem" }}>
      {overlays.map((overlay) => {
        const values = {
          source: overlay.source,
          destination: overlay.destination,
        };
        const text =
          overlay.on_update === "drop"
            ? t("overlays.drop", values)
            : overlay.destination === PACKS_DIR
              ? t("overlays.packsKeep", values)
              : t("overlays.otherKeep", values);
        return (
          <span
            key={overlay.destination}
            role="status"
            style={{
              fontSize: "0.6875rem",
              color:
                overlay.on_update === "keep" ? "var(--c-warn)" : "var(--fg-2)",
            }}
          >
            {text}
          </span>
        );
      })}
    </div>
  );
};
