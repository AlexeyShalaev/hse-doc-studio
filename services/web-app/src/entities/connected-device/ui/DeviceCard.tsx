import { Bot, Cpu, Monitor } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import { Button } from "@shared/ui";
import { StatusDot } from "@shared/ui/StatusDot";
import {
  ACTIVITY_KEY,
  AI_DOT,
  AI_NEEDS_ACTION,
  RUNNER_DOT,
  SYNC_DOT,
  presenceDot,
} from "../lib/deviceLib";
import { commitsText, modelsText, presenceText } from "../lib/deviceText";
import type { AiState, Device, DeviceEndpoint } from "../model/device.schema";

export type DeviceCardProps = {
  device: Device;
  /** Текущее время для подписей «N минут назад»: приходит сверху, чтобы подписи тикали вместе. */
  now: number;
  /** Нет проекта у панели (список аккаунта): состояние проекта не показывается. */
  showProject?: boolean;
  /** Облако может добавить провайдера «через мой раннер»; у локальной Студии такой кнопки нет. */
  onAddProvider?: ((endpoint: DeviceEndpoint) => void) | undefined;
  adding?: boolean;
  /** Кнопки под карточкой (забыть устройство и подобное). */
  actions?: React.ReactNode;
};

const Row = ({
  label,
  children,
  testId,
}: {
  label: string;
  children: React.ReactNode;
  testId?: string;
}) => (
  <div
    className="flex flex-col"
    style={{ gap: 3, padding: "8px 0", borderTop: "1px solid var(--border)" }}
    data-testid={testId}
  >
    <span
      className="dim"
      style={{
        fontSize: 10.5,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
      }}
    >
      {label}
    </span>
    {children}
  </div>
);

const ProjectRows = ({ device, now }: { device: Device; now: number }) => {
  const { t } = useTranslation("devices");
  const project = device.project;
  if (project === null) return null;
  const pdf = project.pdf;
  return (
    <Row label={t("card.project")} testId="device-project">
      <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
        <StatusDot
          status={SYNC_DOT[project.sync]}
          label={t(`card.sync.${project.sync}`)}
        />
        {project.ahead > 0 && (
          <span className="mono dim" style={{ fontSize: 11 }}>
            {t("card.ahead", { commits: commitsText(t, project.ahead) })}
          </span>
        )}
        {project.behind > 0 && (
          <span className="mono dim" style={{ fontSize: 11 }}>
            {t("card.behind", { commits: commitsText(t, project.behind) })}
          </span>
        )}
      </div>
      <span className="dim" style={{ fontSize: 11.5 }}>
        {project.last_sync_at !== null
          ? t("card.lastSync", {
              when: formatPastTime(project.last_sync_at, now),
            })
          : t("card.neverSynced")}
        {" · "}
        {project.auto_sync ? t("card.autoOn") : t("card.autoOff")}
      </span>
      <span
        className="dim"
        style={{
          fontSize: 11.5,
          color: pdf !== null && !pdf.ok ? "var(--c-warn)" : undefined,
        }}
        data-testid="device-pdf"
      >
        {pdf === null
          ? t("card.pdfNone")
          : pdf.ok
            ? t("card.pdfOk", {
                doc: pdf.doc_id,
                when: formatPastTime(pdf.at, now),
              })
            : t("card.pdfFailed", {
                doc: pdf.doc_id,
                when: formatPastTime(pdf.at, now),
              })}
      </span>
    </Row>
  );
};

const RunnerRow = ({ device }: { device: Device }) => {
  const { t } = useTranslation("devices");
  const runner = device.runner;
  return (
    <Row label={t("card.runner")} testId="device-runner">
      {runner === null ? (
        <span className="dim" style={{ fontSize: 11.5 }}>
          {t("card.runnerNone")}
        </span>
      ) : (
        <>
          <div
            className="flex items-center"
            style={{ gap: 8, flexWrap: "wrap" }}
          >
            <StatusDot
              status={RUNNER_DOT[runner.state]}
              label={`${runner.name}: ${t(`card.runnerState.${runner.state}`)}`}
            />
            <span className="dim" style={{ fontSize: 11.5 }}>
              {runner.busy
                ? t("card.runnerBusy", {
                    running: runner.running_jobs,
                    total: runner.concurrency,
                  })
                : t("card.runnerFree")}
            </span>
          </div>
          {runner.tags.length > 0 && (
            <div className="flex" style={{ gap: 4, flexWrap: "wrap" }}>
              {runner.tags.map((tag) => (
                <span key={tag} className="chip sans" style={{ fontSize: 10 }}>
                  {tag}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </Row>
  );
};

const AiEndpointRow = ({
  endpoint,
  onAdd,
  adding,
}: {
  endpoint: DeviceEndpoint;
  onAdd: (() => void) | undefined;
  adding: boolean;
}) => {
  const { t } = useTranslation("devices");
  return (
    <div
      className="flex flex-col"
      style={{
        gap: 3,
        padding: "6px 8px",
        borderRadius: 6,
        background: "var(--bg-2)",
      }}
      data-testid={`device-endpoint-${endpoint.name}`}
      data-state={endpoint.state}
    >
      <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
        <Bot size={12} style={{ color: "var(--fg-2)" }} />
        <span style={{ fontSize: 12, fontWeight: 500 }}>
          {t("ai.endpoint", { name: endpoint.name, flavor: endpoint.flavor })}
        </span>
        <span className="dim" style={{ fontSize: 11 }}>
          {endpoint.reachable === null
            ? t("ai.unchecked")
            : endpoint.reachable
              ? t("ai.reachable")
              : t("ai.unreachable")}
        </span>
      </div>
      <span className="dim" style={{ fontSize: 11.5 }}>
        {endpoint.models.length > 0
          ? modelsText(t, endpoint.models)
          : t("ai.noModels")}
      </span>
      <span className="dim" style={{ fontSize: 11.5 }}>
        {endpoint.provider_name !== null
          ? t("ai.providerYes", { name: endpoint.provider_name })
          : t("ai.providerNo")}
      </span>
      {endpoint.state === "no_provider" && onAdd !== undefined && (
        <div>
          <Button
            variant="primary"
            size="sm"
            onClick={onAdd}
            disabled={adding}
            data-testid="device-add-provider"
          >
            {adding ? t("ai.adding") : t("ai.addInCloud")}
          </Button>
        </div>
      )}
    </div>
  );
};

/** Совет по состоянию ИИ: что человеку сделать, чтобы облако получило модель. */
export const AiAdvice = ({ state }: { state: AiState }) => {
  const { t } = useTranslation("devices");
  if (!AI_NEEDS_ACTION.has(state) && state !== "studio_offline") return null;
  return (
    <span
      style={{ fontSize: 11.5, color: "var(--fg-1)", lineHeight: 1.45 }}
      data-testid="device-ai-advice"
    >
      {t(`ai.advice.${state}`)}
    </span>
  );
};

const AiRow = ({
  device,
  onAddProvider,
  adding,
}: {
  device: Device;
  onAddProvider: DeviceCardProps["onAddProvider"];
  adding: boolean;
}) => {
  const { t } = useTranslation("devices");
  const ai = device.ai;
  return (
    <Row label={t("ai.title")} testId="device-ai">
      <StatusDot status={AI_DOT[ai.state]} label={t(`ai.state.${ai.state}`)} />
      {ai.endpoints.map((endpoint) => (
        <AiEndpointRow
          key={endpoint.name}
          endpoint={endpoint}
          adding={adding}
          onAdd={
            onAddProvider === undefined
              ? undefined
              : () => {
                  onAddProvider(endpoint);
                }
          }
        />
      ))}
      <AiAdvice state={ai.state} />
    </Row>
  );
};

/**
 * Устройство целиком: кто, в сети ли, чем занято, как идёт проект, раннер и ИИ через него. Одна карточка на
 * облако (свои Студии проекта) и на локальную Студию (так облако видит её саму).
 */
export const DeviceCard = ({
  device,
  now,
  showProject = true,
  onAddProvider,
  adding = false,
  actions,
}: DeviceCardProps) => {
  const { t } = useTranslation("devices");
  const online = device.presence === "online";
  return (
    <div
      className="flex flex-col"
      style={{
        gap: 2,
        padding: "10px 12px",
        borderRadius: 8,
        border: "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
      data-testid="device-card"
      data-device={device.id}
      data-presence={device.presence}
    >
      <div className="flex items-center" style={{ gap: 8, minWidth: 0 }}>
        <Monitor size={14} style={{ color: "var(--fg-2)", flexShrink: 0 }} />
        <span
          className="truncate"
          style={{ fontSize: 13, fontWeight: 600 }}
          title={device.name}
          data-testid="device-name"
        >
          {device.name}
        </span>
        <span style={{ marginLeft: "auto", flexShrink: 0 }}>
          <StatusDot
            status={presenceDot(device)}
            label={presenceText(t, device, now)}
          />
        </span>
      </div>
      <div
        className="flex items-center dim"
        style={{ gap: 6, fontSize: 11.5, flexWrap: "wrap" }}
      >
        <Cpu size={11} />
        <span>{t(`os.${device.os}`)}</span>
        <span>·</span>
        <span>{t("version", { version: device.version })}</span>
        {online && (
          <>
            <span>·</span>
            <span data-testid="device-activity" data-activity={device.activity}>
              {t(ACTIVITY_KEY[device.activity])}
            </span>
          </>
        )}
      </div>
      {showProject && <ProjectRows device={device} now={now} />}
      <RunnerRow device={device} />
      <AiRow device={device} onAddProvider={onAddProvider} adding={adding} />
      {actions !== undefined && (
        <div
          className="flex"
          style={{
            gap: 8,
            paddingTop: 8,
            borderTop: "1px solid var(--border)",
          }}
        >
          {actions}
        </div>
      )}
    </div>
  );
};
