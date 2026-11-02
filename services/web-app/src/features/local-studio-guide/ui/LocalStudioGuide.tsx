import { useId, useState } from "react";
import { Link } from "react-router";
import {
  Download,
  ExternalLink,
  Gauge,
  HardDrive,
  Laptop,
  WifiOff,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { i18n } from "@shared/lib";
import { CopyField } from "@shared/ui/CopyField";
import { Notice } from "@shared/ui/ConflictKit";
import { Section } from "@shared/ui/Section";
import { Spinner } from "@shared/ui/Spinner";
import {
  DOCKER_DOWNLOAD,
  INSTALL_OSES,
  detectInstallOs,
  installCommand,
  isValidPort,
  manualCommand,
  studioCloneUrl,
  useLocalStudioInfo,
  useLocalStudioPort,
  type InstallOs,
  type LocalStudioInfo,
} from "@entities/local-studio";
import { gitSettingsPath } from "@entities/git-sync";
import { OpenInLocalStudio } from "./OpenInLocalStudio";

export type LocalStudioGuideProps = {
  /** Проект, ради которого пришли: покажем «Открыть этот проект». */
  projectId?: string | null;
  /** Ссылка на документацию по локальной версии (справка). */
  docsUrl?: string;
};

const userAgent = (): string =>
  typeof navigator === "undefined" ? "" : navigator.userAgent;

/**
 * Экран «Локальная версия» облачной Студии (docs/design/local-from-cloud.md):
 * зачем, что нужно, установка по ОС с адресом этого сервера и подключение
 * к нему кодом устройства. Для проекта ещё «Открыть в локальной Студии».
 */
export const LocalStudioGuide = ({
  projectId = null,
  docsUrl,
}: LocalStudioGuideProps) => {
  const { t } = useTranslation("localStudio");
  const info = useLocalStudioInfo();
  const [port, setPort] = useLocalStudioPort();

  return (
    <div
      className="flex flex-col"
      style={{ gap: 18, width: "100%", maxWidth: 880, padding: "28px 24px" }}
      data-testid="local-studio-guide"
    >
      <header className="flex flex-col" style={{ gap: 6 }}>
        <h1
          className="flex items-center"
          style={{ margin: 0, fontSize: 22, fontWeight: 600, gap: 10 }}
        >
          <Laptop size={22} aria-hidden="true" />
          {t("title")}
        </h1>
        <p className="dim" style={{ margin: 0, fontSize: 13.5, maxWidth: 680 }}>
          {t("lead")}
        </p>
      </header>

      <Why />

      {info.isLoading && (
        <span className="flex items-center dim" style={{ gap: 8 }}>
          <Spinner size="sm" />
          {t("loading")}
        </span>
      )}
      {info.isError && (
        <Notice tone="err" role="alert" text={t("loadFailed")} />
      )}
      {info.data && (
        <>
          <Requirements />
          <Install info={info.data} port={port} onPort={setPort} />
          <Connect info={info.data} port={port} />
          {projectId && (
            <ProjectBlock info={info.data} projectId={projectId} port={port} />
          )}
        </>
      )}

      {docsUrl && (
        <a
          href={docsUrl}
          target="_blank"
          rel="noreferrer noopener"
          className="flex items-center"
          style={{ gap: 6, fontSize: 13 }}
          data-testid="local-studio-docs"
        >
          <ExternalLink size={12} aria-hidden="true" />
          {t("docs")}
        </a>
      )}
    </div>
  );
};

const WHY = [
  { key: "build", Icon: HardDrive },
  { key: "offline", Icon: WifiOff },
  { key: "speed", Icon: Gauge },
] as const;

const Why = () => {
  const { t } = useTranslation("localStudio");
  return (
    <Section title={t("why.title")} testId="local-studio-why">
      <ul
        className="flex flex-col"
        style={{ gap: 10, margin: 0, padding: 0, listStyle: "none" }}
      >
        {WHY.map(({ key, Icon }) => (
          <li key={key} className="flex" style={{ gap: 10, fontSize: 13 }}>
            <Icon
              size={16}
              aria-hidden="true"
              style={{ flexShrink: 0, marginTop: 2, color: "var(--accent)" }}
            />
            <span>
              <strong>{t(`why.${key}.title`)}</strong>
              {" · "}
              <span className="dim">{t(`why.${key}.text`)}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="dim" style={{ margin: "10px 0 0", fontSize: 12.5 }}>
        {t("why.sync")}
      </p>
    </Section>
  );
};

const Requirements = () => {
  const { t } = useTranslation("localStudio");
  return (
    <Section title={t("requirements.title")} testId="local-studio-requirements">
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>
        <li>{t("requirements.docker")}</li>
        <li>{t("requirements.disk")}</li>
        <li>{t("requirements.memory")}</li>
        <li>{t("requirements.browser")}</li>
      </ul>
    </Section>
  );
};

const Install = ({
  info,
  port,
  onPort,
}: {
  info: LocalStudioInfo;
  port: number;
  onPort: (port: number) => void;
}) => {
  const { t } = useTranslation("localStudio");
  const uid = useId();
  const [os, setOs] = useState<InstallOs>(() => detectInstallOs(userAgent()));
  const [pin, setPin] = useState(false);
  const [portText, setPortText] = useState(String(port));
  const lang = i18n.language === "en" ? "en" : "ru";
  const input = {
    os,
    installBaseUrl: info.install_base_url,
    image: info.image,
    serverUrl: info.server_url,
    port,
    tag: pin ? info.recommended_tag : null,
    lang,
  } as const;
  const portInvalid = !isValidPort(Number(portText));

  return (
    <Section
      title={t("install.title")}
      description={t("install.lead")}
      testId="local-studio-install"
    >
      <div className="flex flex-col" style={{ gap: 12 }}>
        <div
          className="seg"
          role="tablist"
          aria-label={t("install.osLabel")}
          style={{ alignSelf: "flex-start" }}
        >
          {INSTALL_OSES.map((value) => (
            <button
              key={value}
              type="button"
              role="tab"
              id={`${uid}-tab-${value}`}
              aria-selected={os === value}
              aria-controls={`${uid}-panel`}
              className={os === value ? "active" : undefined}
              onClick={() => {
                setOs(value);
              }}
              data-testid={`local-studio-os-${value}`}
            >
              {t(`install.os.${value}`)}
            </button>
          ))}
        </div>
        <div
          role="tabpanel"
          id={`${uid}-panel`}
          aria-labelledby={`${uid}-tab-${os}`}
          className="flex flex-col"
          style={{ gap: 10, fontSize: 13 }}
        >
          <ol style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
            <li>
              {t(`install.docker.${os}`)}{" "}
              <a
                href={DOCKER_DOWNLOAD[os]}
                target="_blank"
                rel="noreferrer noopener"
              >
                {t("install.dockerLink")}
              </a>
            </li>
            <li>{t(`install.terminal.${os}`)}</li>
          </ol>
          <div data-testid="local-studio-install-command">
            <CopyField
              value={installCommand(input)}
              label={t("install.command")}
              multiline
              wrap="spaces"
            />
          </div>
          <span className="dim" style={{ fontSize: 12.5 }}>
            {t("install.after")}
          </span>
          <div className="flex items-end" style={{ gap: 16, flexWrap: "wrap" }}>
            <label className="flex flex-col" style={{ gap: 4, fontSize: 12.5 }}>
              {t("install.port")}
              <input
                className="input mono"
                inputMode="numeric"
                value={portText}
                aria-invalid={portInvalid}
                style={{ width: 110 }}
                onChange={(event) => {
                  setPortText(event.target.value);
                  const next = Number(event.target.value);
                  if (isValidPort(next)) onPort(next);
                }}
                data-testid="local-studio-port"
              />
            </label>
            {info.recommended_tag && (
              <label
                className="flex items-center"
                style={{ gap: 6, fontSize: 12.5, paddingBottom: 6 }}
              >
                <input
                  type="checkbox"
                  checked={pin}
                  onChange={(event) => {
                    setPin(event.target.checked);
                  }}
                  data-testid="local-studio-pin"
                />
                {t("install.pin", { tag: info.recommended_tag })}
              </label>
            )}
          </div>
          <span className="dim" style={{ fontSize: 12 }}>
            {t("install.portHint")}
          </span>
          <details>
            <summary style={{ cursor: "pointer", fontSize: 12.5 }}>
              {t("install.manual")}
            </summary>
            <div
              className="flex flex-col"
              style={{ gap: 8, marginTop: 8 }}
              data-testid="local-studio-manual-command"
            >
              <CopyField
                value={manualCommand(input)}
                label={t("install.manualCommand")}
                multiline
                wrap="spaces"
              />
              <span className="dim" style={{ fontSize: 12 }}>
                {t("install.manualAfter", { port })}
              </span>
            </div>
          </details>
          <a
            href={info.releases_url}
            target="_blank"
            rel="noreferrer noopener"
            className="flex items-center"
            style={{ gap: 6, fontSize: 12.5, alignSelf: "flex-start" }}
            data-testid="local-studio-releases"
          >
            <Download size={12} aria-hidden="true" />
            {t("install.releases")}
          </a>
        </div>
      </div>
    </Section>
  );
};

const Connect = ({ info, port }: { info: LocalStudioInfo; port: number }) => {
  const { t } = useTranslation("localStudio");
  return (
    <Section
      title={t("connect.title")}
      description={t("connect.lead")}
      testId="local-studio-connect"
    >
      <div className="flex flex-col" style={{ gap: 12, fontSize: 13 }}>
        {!info.git_remote_enabled && (
          <Notice tone="warn" role="status" text={t("connect.disabled")} />
        )}
        <ol style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
          <li>{t("connect.step1")}</li>
          <li>{t("connect.step2")}</li>
          <li>{t("connect.step3")}</li>
        </ol>
        {info.git_remote_enabled && (
          <div
            className="flex items-center"
            style={{ gap: 10, flexWrap: "wrap" }}
          >
            <OpenInLocalStudio port={port} />
            <span className="dim" style={{ fontSize: 12 }}>
              {t("connect.buttonHint", { port })}
            </span>
          </div>
        )}
        <div data-testid="local-studio-server-url">
          <CopyField value={info.server_url} label={t("connect.serverUrl")} />
        </div>
        <span className="dim" style={{ fontSize: 12 }}>
          {t("connect.manual")}
        </span>
        <Notice
          tone="info"
          text={t("connect.version", { version: info.server_version })}
        />
      </div>
    </Section>
  );
};

const ProjectBlock = ({
  info,
  projectId,
  port,
}: {
  info: LocalStudioInfo;
  projectId: string;
  port: number;
}) => {
  const { t } = useTranslation("localStudio");
  return (
    <Section
      title={t("project.title")}
      description={t("project.lead")}
      testId="local-studio-project"
    >
      <div className="flex flex-col" style={{ gap: 10 }}>
        {info.git_remote_enabled && (
          <div style={{ alignSelf: "flex-start" }}>
            <OpenInLocalStudio projectId={projectId} port={port} />
          </div>
        )}
        <CopyField
          value={studioCloneUrl(info.server_url, projectId)}
          label={t("project.cloneUrl")}
        />
        <Link to={gitSettingsPath(projectId)} style={{ fontSize: 12.5 }}>
          {t("project.settings")}
        </Link>
      </div>
    </Section>
  );
};
