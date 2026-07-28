import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy, Terminal } from "lucide-react";
import { DEFAULT_FOLDER_NAME, detectHostOs } from "@features/first-run-setup";

type ManualCommandProps = {
  hostPath: string;
  /** gid владельца docker-сокета, если приложение сумело его прочитать. */
  socketGid?: string | undefined;
};

const CONTAINER_NAME = "hse-doc-studio";

/**
 * Запасной путь: команда для терминала, если пересоздать себя мы не можем.
 *
 * Такое бывает, когда сокет докера не проброшен внутрь или недоступен по
 * правам — тогда приложение бессильно по определению: оно не может ни создать
 * контейнер, ни удалить себя. Оставлять человека наедине с этим нельзя, поэтому
 * собираем готовую строку с уже подставленными папкой и группой сокета.
 */
export const ManualCommand = ({ hostPath, socketGid }: ManualCommandProps) => {
  const { t } = useTranslation("setup");
  const [copied, setCopied] = useState(false);
  const os = detectHostOs();

  const path =
    hostPath.trim() ||
    (os === "windows"
      ? `C:/Users/me/${DEFAULT_FOLDER_NAME}`
      : `~/${DEFAULT_FOLDER_NAME}`);
  // Процесс в контейнере непривилегированный, а сокет приезжает с правами
  // ВЛАДЕЛЬЦА С ХОСТА — без членства в его группе любое обращение к докеру
  // падает с «permission denied», то есть не собирается ни один документ. gid мы
  // прочитали сами (stat сокета доступен и без права им пользоваться); не
  // прочитали — 0 верен для Docker Desktop, где сокет принадлежит root:root.
  const gid = socketGid ?? "0";
  // Одна строка на все ОС: PowerShell, cmd и sh одинаково понимают её без
  // переносов, а перенос строки — главный источник «скопировал не целиком».
  const command = [
    `docker run -d --name ${CONTAINER_NAME} --restart unless-stopped`,
    "-p 17240:8000",
    "-v /var/run/docker.sock:/var/run/docker.sock",
    `--group-add ${gid}`,
    `-v "${path}:/data"`,
    "-e HSE_STUDIO__DATA_DIR=/data",
    `-e HSE_STUDIO__HOST_DATA_DIR="${path}"`,
    "--add-host=host.docker.internal:host-gateway",
    "ghcr.io/alexeyshalaev/hse-doc-studio:latest",
  ].join(" ");

  const handleCopy = () => {
    void navigator.clipboard.writeText(command).then(() => {
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
      }, 2_000);
    });
  };

  return (
    <div
      style={{
        marginTop: 18,
        padding: "12px 14px",
        borderRadius: 8,
        background: "var(--bg-2, var(--bg))",
        border: "1px solid var(--border)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 8,
        }}
      >
        <Terminal size={14} style={{ opacity: 0.7 }} />
        <span style={{ fontWeight: 600, fontSize: 13 }}>
          {t("manual.title")}
        </span>
        <button
          type="button"
          className="btn xs"
          onClick={handleCopy}
          style={{ marginLeft: "auto" }}
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? t("manual.copied") : t("manual.copy")}
        </button>
      </div>
      <div className="dim" style={{ fontSize: 12, marginBottom: 8 }}>
        {t("manual.hint")}
      </div>
      <code
        style={{
          display: "block",
          fontSize: 11,
          lineHeight: 1.6,
          whiteSpace: "pre-wrap",
          wordBreak: "break-all",
          userSelect: "all",
        }}
      >
        {command}
      </code>
    </div>
  );
};
