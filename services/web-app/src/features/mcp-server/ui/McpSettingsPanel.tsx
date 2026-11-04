import { useId, useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { i18n, localeTag } from "@shared/lib";
import {
  Badge,
  DataTable,
  ErrorState,
  Section,
  SettingRow,
  Spinner,
} from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import { Notice } from "@shared/ui/ConflictKit";
import type { McpScope } from "../api/mcpApi";
import {
  useMcpCalls,
  useMcpSettings,
  useSaveMcpSettings,
} from "../api/queries";
import type {
  McpCall,
  McpSettings,
  McpSettingsChange,
  McpTool,
  McpToolGroup,
} from "../api/schemas";
import { groupTools, toggled } from "../lib/configs";

const failureText = (error: unknown): string => {
  const key = `errors:code.${failureCode(error)}`;
  return i18n.exists(key) ? i18n.t(key) : i18n.t("mcp:failure.unknown");
};

const toolChecked = (settings: McpSettings, tool: McpTool): boolean =>
  !settings.disabled_tools.includes(tool.name) &&
  (!tool.dangerous || settings.enabled_dangerous.includes(tool.name));

const ToolRow = ({
  tool,
  checked,
  disabled,
  onChange,
}: {
  tool: McpTool;
  checked: boolean;
  disabled: boolean;
  onChange: (next: boolean) => void;
}) => {
  const { t } = useTranslation("mcp");
  const id = useId();
  return (
    <SettingRow
      htmlFor={id}
      label={
        <span
          className="flex items-center"
          style={{ gap: "0.375rem", flexWrap: "wrap" }}
        >
          <code>{tool.name}</code>
          {tool.kind === "read" && (
            <Badge variant="subtle">{t("badge.readOnly")}</Badge>
          )}
          {tool.dangerous && (
            <Badge variant="warning">{t("badge.dangerous")}</Badge>
          )}
          {tool.admin && <Badge variant="subtle">{t("badge.admin")}</Badge>}
        </span>
      }
      hint={tool.description}
    >
      <Switch
        id={id}
        checked={checked}
        disabled={disabled}
        onChange={onChange}
        testId={`mcp-tool-${tool.name}`}
      />
    </SettingRow>
  );
};

const GroupBlock = ({
  group,
  tools,
  settings,
  busy,
  save,
}: {
  group: McpToolGroup;
  tools: McpTool[];
  settings: McpSettings;
  busy: boolean;
  save: (change: McpSettingsChange) => void;
}) => {
  const { t } = useTranslation("mcp");
  const groupOn = !settings.disabled_groups.includes(group);
  return (
    <Section
      title={t(`group.${group}.title`)}
      description={t(`group.${group}.hint`)}
      actions={
        <Switch
          checked={groupOn}
          disabled={busy}
          label={t("groupToggle", { group: t(`group.${group}.title`) })}
          onChange={(on) => {
            save({
              disabled_groups: toggled(settings.disabled_groups, group, !on),
            });
          }}
          testId={`mcp-group-${group}`}
        />
      }
    >
      {tools.map((tool) => (
        <ToolRow
          key={tool.name}
          tool={tool}
          checked={toolChecked(settings, tool)}
          disabled={busy || !groupOn}
          onChange={(on) => {
            save(
              tool.dangerous && on
                ? {
                    enabled_dangerous: toggled(
                      settings.enabled_dangerous,
                      tool.name,
                      true,
                    ),
                    disabled_tools: toggled(
                      settings.disabled_tools,
                      tool.name,
                      false,
                    ),
                  }
                : tool.dangerous
                  ? {
                      enabled_dangerous: toggled(
                        settings.enabled_dangerous,
                        tool.name,
                        false,
                      ),
                    }
                  : {
                      disabled_tools: toggled(
                        settings.disabled_tools,
                        tool.name,
                        !on,
                      ),
                    },
            );
          }}
        />
      ))}
    </Section>
  );
};

const OUTCOME_TONE: Record<
  McpCall["outcome"],
  "success" | "error" | "warning"
> = {
  ok: "success",
  error: "error",
  denied: "warning",
};

const CallsTable = ({
  calls,
  loading,
}: {
  calls: McpCall[];
  loading: boolean;
}) => {
  const { t } = useTranslation("mcp");
  const columns = useMemo<ColumnDef<McpCall>[]>(
    () => [
      {
        id: "at",
        header: t("journal.at"),
        enableSorting: false,
        cell: ({ row }) =>
          new Date(row.original.at).toLocaleString(localeTag()),
      },
      {
        id: "tool",
        header: t("journal.tool"),
        enableSorting: false,
        cell: ({ row }) => <code>{row.original.tool}</code>,
      },
      {
        id: "who",
        header: t("journal.who"),
        enableSorting: false,
        cell: ({ row }) =>
          row.original.actor_name ?? row.original.actor_id ?? "—",
      },
      {
        id: "outcome",
        header: t("journal.outcome"),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="flex items-center" style={{ gap: "0.375rem" }}>
            <Badge variant={OUTCOME_TONE[row.original.outcome]}>
              {t(`journal.outcomes.${row.original.outcome}`)}
            </Badge>
            {row.original.error_code && (
              <span className="dim">{row.original.error_code}</span>
            )}
          </span>
        ),
      },
      {
        id: "duration",
        header: t("journal.duration"),
        enableSorting: false,
        cell: ({ row }) => t("journal.ms", { value: row.original.duration_ms }),
      },
    ],
    [t],
  );
  return (
    <DataTable
      columns={columns}
      data={calls}
      getRowId={(row) => `${row.at}-${row.tool}-${row.actor_id ?? ""}`}
      caption={t("journal.title")}
      loading={loading}
      emptyTitle={t("journal.empty")}
    />
  );
};

/**
 * Настройки MCP-сервера: общий переключатель, группы и тулы, журнал вызовов.
 * Один компонент для админки облака (scope admin) и локальной Студии (local).
 */
export const McpSettingsPanel = ({ scope }: { scope: McpScope }) => {
  const { t } = useTranslation("mcp");
  const settings = useMcpSettings(scope);
  const save = useSaveMcpSettings(scope);
  const calls = useMcpCalls(scope, settings.data?.enabled ?? false);
  const [error, setError] = useState<string | null>(null);
  const masterId = useId();

  if (settings.isPending) return <Spinner />;
  if (settings.isError) {
    return (
      <ErrorState
        title={failureText(settings.error)}
        onRetry={() => void settings.refetch()}
      />
    );
  }
  const data = settings.data;
  const apply = (change: McpSettingsChange) => {
    setError(null);
    save.mutate(change, {
      onError: (e) => {
        setError(failureText(e));
      },
    });
  };

  return (
    <div
      className="flex flex-col"
      style={{ gap: "1rem" }}
      data-testid="mcp-settings"
    >
      <Section>
        <SettingRow
          label={t("enable.label")}
          hint={t("enable.hint")}
          htmlFor={masterId}
        >
          <Switch
            id={masterId}
            checked={data.enabled}
            disabled={save.isPending}
            onChange={(on) => {
              apply({ enabled: on });
            }}
            testId="mcp-enabled"
          />
        </SettingRow>
      </Section>
      {error && <Notice tone="err" role="alert" text={error} />}
      <p className="dim" style={{ margin: 0 }}>
        {t("tools.lead")}
      </p>
      {groupTools(data.tools).map(({ group, tools }) => (
        <GroupBlock
          key={group}
          group={group}
          tools={tools}
          settings={data}
          busy={save.isPending}
          save={apply}
        />
      ))}
      <Section title={t("journal.title")} description={t("journal.hint")} flush>
        {data.enabled ? (
          <CallsTable calls={calls.data ?? []} loading={calls.isPending} />
        ) : (
          <p className="dim" style={{ padding: "0 1rem" }}>
            {t("journal.off")}
          </p>
        )}
      </Section>
    </div>
  );
};
