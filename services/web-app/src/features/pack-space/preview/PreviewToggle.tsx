import { Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSpaceNav } from "../context/useSpaceNav";
import { previewPatch } from "./link";

/** «Предпросмотр PDF» / «Скрыть предпросмотр» в кнопках панели «Подробности» (5.4). */
export const PreviewToggle = ({ open }: { open: boolean }) => {
  const { t } = useTranslation("packSpace");
  const nav = useSpaceNav();
  const Icon = open ? EyeOff : Eye;
  return (
    <button
      type="button"
      className="btn"
      aria-pressed={open}
      data-testid="sp-preview-toggle"
      onClick={() => {
        nav.go(previewPatch(!open));
      }}
    >
      <Icon size="0.875rem" aria-hidden="true" />
      {open ? t("preview.hide") : t("preview.show")}
    </button>
  );
};
