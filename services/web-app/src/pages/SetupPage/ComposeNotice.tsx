import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

type ComposeNoticeProps = {
  project: string;
  path: string;
};

/**
 * Установка поднята docker compose — чинить её мастером НЕЛЬЗЯ.
 *
 * Пересоздать контейнер мы бы смогли, но файл и `.env` остались бы прежними, и
 * первый же `docker compose up -d` вернул старую конфигурацию. Человек при этом
 * решил бы, что приложение забыло его папку — ровно то молчаливое поведение,
 * ради устранения которого мастер и появился. Поэтому показываем строку,
 * которую надо поправить.
 */
export const ComposeNotice = ({ project, path }: ComposeNoticeProps) => {
  const { t } = useTranslation("setup");

  return (
    <div
      style={{
        padding: "14px 16px",
        borderRadius: 10,
        background: "var(--c-info-soft)",
        border: "1px solid var(--c-info)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 4,
        }}
      >
        <Info size={15} style={{ color: "var(--c-info)", flexShrink: 0 }} />
        <span style={{ fontWeight: 600, color: "var(--c-info)" }}>
          {t("compose.title", { project })}
        </span>
      </div>
      <p className="dim" style={{ fontSize: 12.5, margin: "0 0 10px 23px" }}>
        {t("compose.hint")}
      </p>
      <code
        style={{
          display: "block",
          marginLeft: 23,
          fontSize: 11.5,
          lineHeight: 1.8,
          whiteSpace: "pre-wrap",
          wordBreak: "break-all",
          userSelect: "all",
        }}
      >
        {`DATA_DIR=${path}\ndocker compose up -d`}
      </code>
    </div>
  );
};
