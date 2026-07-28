import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, Download, Search } from "lucide-react";
import {
  catKey,
  cssFallback,
  FONT_SAMPLE,
  MARKETPLACE_CATEGORIES,
  useGoogleFontsStylesheet,
  useInstallMarketplaceFont,
  useMarketplaceSearch,
  type MarketplaceFont,
} from "@entities/fonts";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";

const PAGE_SIZE = 24;
const SEARCH_DEBOUNCE_MS = 300;

// ── One marketplace font card ─────────────────────────────────────────────────

type MarketplaceCardProps = {
  font: MarketplaceFont;
};

const MarketplaceCard = ({ font }: MarketplaceCardProps) => {
  const { t } = useTranslation("settings");
  const install = useInstallMarketplaceFont();

  const handleInstall = () => {
    install.mutate(font.id, {
      onSuccess: () =>
        toast.success(
          t("fonts.marketplaceInstalledToast", { name: font.family }),
        ),
      onError: (err) => toast.error(String(err)),
    });
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "10px 12px",
        borderRadius: 6,
        border: "1px solid var(--border)",
        background: "var(--bg-2)",
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: `'${font.family}', ${cssFallback(font.category)}`,
            fontSize: 19,
            lineHeight: 1.3,
            color: "var(--fg-0)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={FONT_SAMPLE}
        >
          {FONT_SAMPLE}
        </div>
        <div
          className="flex items-center"
          style={{ gap: 8, marginTop: 4, flexWrap: "wrap" }}
        >
          <span style={{ fontSize: 12, fontWeight: 500 }}>{font.family}</span>
          <span className="chip" style={{ fontSize: 10 }}>
            {t(`fonts.cat.${catKey(font.category)}`, {
              defaultValue: font.category,
            })}
          </span>
          {font.cyrillic && (
            <span className="chip" style={{ fontSize: 10 }}>
              {t("fonts.cyrillicBadge")}
            </span>
          )}
          <span style={{ fontSize: 10.5, color: "var(--fg-3)" }}>
            {t("fonts.marketplaceWeights", { count: font.file_count })}
          </span>
        </div>
      </div>
      <button
        className="btn btn-secondary"
        onClick={handleInstall}
        disabled={install.isPending}
        style={{ fontSize: 12, gap: 6, flexShrink: 0 }}
      >
        {install.isPending ? <Spinner size="sm" /> : <Download size={14} />}
        {t("fonts.install")}
      </button>
    </div>
  );
};

// ── Google Fonts source ───────────────────────────────────────────────────────

export const GoogleFontsSource = () => {
  const { t } = useTranslation("settings");
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [cyrillicOnly, setCyrillicOnly] = useState(true);
  const [limit, setLimit] = useState(PAGE_SIZE);

  useEffect(() => {
    const id = setTimeout(() => {
      // A settled new query is a new search → back to the first page.
      setDebounced(query);
      setLimit(PAGE_SIZE);
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      clearTimeout(id);
    };
  }, [query]);

  const { data, isFetching } = useMarketplaceSearch({
    q: debounced,
    category,
    cyrillic: cyrillicOnly,
    limit,
  });

  const items = useMemo(() => data?.items ?? [], [data]);
  const total = data?.total ?? 0;

  const families = useMemo(() => items.map((f) => f.family), [items]);
  useGoogleFontsStylesheet(families);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <p style={{ fontSize: 11.5, color: "var(--fg-3)", margin: 0 }}>
        {t("fonts.marketplaceHint")}
      </p>

      {/* Controls */}
      <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap" }}>
        <div
          className="flex items-center"
          style={{
            gap: 6,
            padding: "5px 8px",
            border: "1px solid var(--border)",
            borderRadius: 6,
            background: "var(--bg-2)",
            flex: 1,
            minWidth: 180,
          }}
        >
          <Search size={13} style={{ color: "var(--fg-3)", flexShrink: 0 }} />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
            }}
            placeholder={t("fonts.marketplaceSearch")}
            style={{
              flex: 1,
              border: "none",
              background: "transparent",
              outline: "none",
              fontSize: 12,
              color: "var(--fg-0)",
            }}
          />
        </div>
        <select
          className="input"
          value={category ?? ""}
          onChange={(e) => {
            setCategory(e.target.value || null);
            setLimit(PAGE_SIZE);
          }}
          style={{ fontSize: 12, width: "auto" }}
        >
          <option value="">{t("fonts.marketplaceCatAll")}</option>
          {MARKETPLACE_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {t(`fonts.cat.${catKey(c)}`)}
            </option>
          ))}
        </select>
        <label
          className="flex items-center"
          style={{
            gap: 6,
            fontSize: 12,
            color: "var(--fg-1)",
            cursor: "pointer",
          }}
        >
          <input
            type="checkbox"
            checked={cyrillicOnly}
            onChange={(e) => {
              setCyrillicOnly(e.target.checked);
              setLimit(PAGE_SIZE);
            }}
          />
          {t("fonts.marketplaceCyrillicOnly")}
        </label>
      </div>

      {/* Results */}
      {isFetching && items.length === 0 ? (
        <Spinner size="sm" />
      ) : items.length === 0 ? (
        <p style={{ fontSize: 12, color: "var(--fg-3)", margin: "4px 0" }}>
          {t("fonts.marketplaceEmpty")}
        </p>
      ) : (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {items.map((f) => (
              <MarketplaceCard key={f.id} font={f} />
            ))}
          </div>
          <div
            className="flex items-center justify-between"
            style={{ marginTop: 2 }}
          >
            <span style={{ fontSize: 11, color: "var(--fg-3)" }}>
              {t("fonts.marketplaceCount", { shown: items.length, total })}
            </span>
            {items.length < total && (
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setLimit((n) => n + PAGE_SIZE);
                }}
                disabled={isFetching}
                style={{ fontSize: 12, gap: 6 }}
              >
                {isFetching ? <Spinner size="sm" /> : <ChevronDown size={14} />}
                {t("fonts.marketplaceLoadMore")}
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
};
