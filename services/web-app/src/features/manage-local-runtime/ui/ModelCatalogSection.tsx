import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, Search, Trash2, X } from "lucide-react";
import {
  useSearchRegistry,
  type CatalogModel,
  type ModelCatalog,
} from "@entities/ai-runtime";
import { Spinner } from "@shared/ui/Spinner";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import { ModelRow } from "./ModelRow";
import { RegistryModelRow } from "./RegistryModelRow";

// A plausible `ollama pull` reference: optional namespace, name, optional :tag.
const MODEL_REF = /^[a-z0-9][a-z0-9._/-]*(:[a-z0-9._-]+)?$/i;
const SEARCH_DEBOUNCE_MS = 350;
const MIN_SEARCH_LEN = 2;

const Label = ({ children }: { children: React.ReactNode }) => (
  <div
    className="dim"
    style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}
  >
    {children}
  </div>
);

export type ModelCatalogSectionProps = {
  catalog: ModelCatalog | undefined;
  isLoading: boolean;
  installedModels: string[];
  canInstall: boolean;
  busy: boolean;
  onInstall: (name: string) => void;
  onDelete: (name: string) => void;
};

export const ModelCatalogSection = ({
  catalog,
  isLoading,
  installedModels,
  canInstall,
  busy,
  onInstall,
  onDelete,
}: ModelCatalogSectionProps) => {
  const { t } = useTranslation("localRuntime");
  const [query, setQuery] = useState("");
  const debounced = useDebouncedValue(query.trim(), SEARCH_DEBOUNCE_MS);
  const registryQuery = useSearchRegistry(debounced);

  const installedSet = new Set(installedModels);
  const isInstalled = (name: string): boolean =>
    installedSet.has(name) ||
    installedModels.some((m) => m.startsWith(`${name}:`));

  const allModels = catalog?.models ?? [];
  const allowCustom = catalog?.allow_custom ?? false;
  const q = debounced.toLowerCase();

  const filteredCatalog = q
    ? allModels.filter((m) =>
        `${m.name} ${m.label} ${m.family} ${m.tasks.join(" ")}`
          .toLowerCase()
          .includes(q),
      )
    : allModels;

  const catalogBaseNames = new Set(allModels.map((m) => m.name.split(":")[0]));
  const registryResults = (registryQuery.data?.models ?? []).filter(
    (m) => !catalogBaseNames.has(m.name),
  );

  const typed = query.trim();
  const showCustom =
    allowCustom &&
    typed.length > 0 &&
    MODEL_REF.test(typed) &&
    !allModels.some((m) => m.name === typed) &&
    !registryResults.some((m) => m.name === typed);

  const searching = debounced.length >= MIN_SEARCH_LEN;
  const installDisabled = busy || !canInstall;

  // Only block a catalog model when we actually KNOW it won't fit (hardware
  // detected + not runnable). With unknown hardware everything is "not runnable"
  // by default, so we must NOT disable then — let the user decide.
  const hardwareKnown = (catalog?.hardware.total_ram_mb ?? null) !== null;
  const isUnfit = (m: CatalogModel): boolean => hardwareKnown && !m.runnable;
  const rowDisabled = (m: CatalogModel): boolean =>
    installDisabled || isUnfit(m);
  const rowReason = (m: CatalogModel): string | undefined =>
    canInstall && isUnfit(m) ? t("catalog.notEnoughMemory") : undefined;

  return (
    <div className="flex flex-col" style={{ gap: 8 }}>
      {installedModels.length > 0 && (
        <div className="flex flex-col" style={{ gap: 6 }}>
          <Label>{t("catalog.installedModels")}</Label>
          {installedModels.map((name) => (
            <div
              key={name}
              className="flex items-center justify-between"
              style={{
                gap: 12,
                padding: "8px 12px",
                borderRadius: 6,
                border: "1px solid var(--border)",
                background: "var(--bg-1)",
              }}
            >
              <span className="mono" style={{ fontSize: 12 }}>
                {name}
              </span>
              <button
                type="button"
                className="btn xs"
                onClick={() => {
                  onDelete(name);
                }}
                disabled={busy}
                title={t("catalog.deleteModelTitle")}
              >
                <Trash2 size={11} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Search box */}
      <div
        className="flex items-center"
        style={{
          gap: 8,
          padding: "6px 10px",
          borderRadius: 6,
          border: "1px solid var(--border)",
          background: "var(--bg-1)",
        }}
      >
        <Search size={13} style={{ color: "var(--fg-2)", flexShrink: 0 }} />
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
          }}
          placeholder={t("catalog.searchPlaceholder")}
          style={{
            flex: 1,
            minWidth: 0,
            border: "none",
            background: "transparent",
            outline: "none",
            fontSize: 12,
            color: "var(--fg-0)",
          }}
        />
        {query && (
          <button
            type="button"
            className="icon-btn"
            onClick={() => {
              setQuery("");
            }}
            title={t("catalog.clear")}
          >
            <X size={12} />
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
          <Spinner size="sm" />
          <span className="dim">{t("catalog.matchingHardware")}</span>
        </div>
      ) : !searching ? (
        <div className="flex flex-col" style={{ gap: 6 }}>
          <Label>{t("catalog.catalog")}</Label>
          {filteredCatalog.map((m) => (
            <ModelRow
              key={m.name}
              model={m}
              installed={isInstalled(m.name)}
              disabled={rowDisabled(m)}
              disabledReason={rowReason(m)}
              onInstall={() => {
                onInstall(m.name);
              }}
            />
          ))}
        </div>
      ) : (
        <div className="flex flex-col" style={{ gap: 8 }}>
          {filteredCatalog.length > 0 && (
            <div className="flex flex-col" style={{ gap: 6 }}>
              <Label>{t("catalog.fromCatalog")}</Label>
              {filteredCatalog.map((m) => (
                <ModelRow
                  key={m.name}
                  model={m}
                  installed={isInstalled(m.name)}
                  disabled={rowDisabled(m)}
                  disabledReason={rowReason(m)}
                  onInstall={() => {
                    onInstall(m.name);
                  }}
                />
              ))}
            </div>
          )}

          <div className="flex flex-col" style={{ gap: 6 }}>
            <div className="flex items-center" style={{ gap: 8 }}>
              <Label>{t("catalog.fromRegistry")}</Label>
              {registryQuery.isFetching && <Spinner size="sm" />}
            </div>

            {showCustom && (
              <button
                type="button"
                className="btn xs"
                onClick={() => {
                  onInstall(typed);
                }}
                disabled={installDisabled}
                style={{ alignSelf: "flex-start" }}
              >
                <Download size={11} />
                {t("catalog.installExact", { name: typed })}
              </button>
            )}

            {registryResults.map((m) => (
              <RegistryModelRow
                key={m.name}
                model={m}
                installed={isInstalled(m.name)}
                busy={installDisabled}
                onInstall={() => {
                  onInstall(m.name);
                }}
              />
            ))}

            {!registryQuery.isFetching &&
              registryResults.length === 0 &&
              !showCustom && (
                <span className="dim" style={{ fontSize: 11 }}>
                  {registryQuery.isError
                    ? t("catalog.registryUnavailable")
                    : t("catalog.nothingFound")}
                </span>
              )}
          </div>
        </div>
      )}
    </div>
  );
};
