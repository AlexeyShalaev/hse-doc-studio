import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp, SlidersHorizontal } from "lucide-react";

import type { HseFacetOption, HseFacetsResponse } from "../api";
import { SearchableSelect } from "./SearchableSelect";

export type HsePersonFilterState = {
  campus: string;
  udept: string;
  ltr: string;
  category: string;
  scirank: string;
  position: string;
  intst: string;
};

export type HsePersonFiltersProps = {
  facets: HseFacetsResponse | undefined;
  interests: HseFacetOption[];
  value: HsePersonFilterState;
  onChange: (patch: Partial<HsePersonFilterState>) => void;
};

const CAMPUS_KEYS = ["moscow", "spb", "nn", "perm"] as const;
const CYRILLIC_LETTERS = Array.from("АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЭЮЯ");

const fieldLabelStyle: React.CSSProperties = {
  fontSize: "0.65625rem",
  color: "var(--fg-3)",
};
const selectStyle: React.CSSProperties = {
  fontSize: "0.75rem",
  padding: "0.375rem 0.4375rem",
  minWidth: 0,
};

type FacetSelectProps = {
  label: string;
  value: string;
  options: HseFacetOption[];
  allLabel: string;
  onChange: (value: string) => void;
};

const FacetSelect = ({
  label,
  value,
  options,
  allLabel,
  onChange,
}: FacetSelectProps) => (
  <label className="field" style={{ gap: "0.1875rem", minWidth: 0 }}>
    <span style={fieldLabelStyle}>{label}</span>
    <select
      className="input"
      style={selectStyle}
      value={value}
      onChange={(e) => {
        onChange(e.target.value);
      }}
    >
      <option value="">{allLabel}</option>
      {options.map((o) => (
        <option key={o.value || o.label} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  </label>
);

export const HsePersonFilters = ({
  facets,
  interests,
  value,
  onChange,
}: HsePersonFiltersProps) => {
  const { t } = useTranslation("hsePerson");
  const all = t("filters.all");
  const hasSecondary =
    value.ltr !== "" ||
    value.category !== "" ||
    value.scirank !== "" ||
    value.position !== "";
  const [showMore, setShowMore] = useState(hasSecondary);

  return (
    <div className="flex flex-col" style={{ gap: "0.625rem" }}>
      {/* Campus — a segmented pill row (4 fixed campuses). */}
      <div className="flex flex-col" style={{ gap: "0.25rem" }}>
        <span style={fieldLabelStyle}>{t("filters.campus")}</span>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
          {CAMPUS_KEYS.map((key) => {
            const active = value.campus === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => {
                  onChange({ campus: key, udept: "" });
                }}
                style={{
                  fontSize: "0.75rem",
                  padding: "0.3125rem 0.75rem",
                  borderRadius: "999px",
                  cursor: "pointer",
                  border: active
                    ? "1px solid var(--accent)"
                    : "1px solid var(--border)",
                  color: active ? "var(--accent)" : "var(--fg-1)",
                  background: active
                    ? "color-mix(in srgb, var(--accent) 12%, transparent)"
                    : "var(--bg-2)",
                }}
              >
                {t(`filters.campusNames.${key}`)}
              </button>
            );
          })}
        </div>
      </div>

      {/* Department — a searchable combobox (the list is huge). */}
      <label className="field" style={{ gap: "0.1875rem", minWidth: 0 }}>
        <span style={fieldLabelStyle}>{t("filters.department")}</span>
        <SearchableSelect
          value={value.udept}
          options={facets?.departments ?? []}
          placeholder={t("filters.departmentPlaceholder")}
          emptyText={t("filters.departmentEmpty")}
          onChange={(v) => {
            onChange({ udept: v });
          }}
        />
      </label>

      {/* Secondary facets — tucked away to keep the modal calm. */}
      <button
        type="button"
        className="btn xs ghost"
        onClick={() => {
          setShowMore((v) => !v);
        }}
        style={{ alignSelf: "flex-start", gap: "0.375rem" }}
      >
        <SlidersHorizontal size="0.75rem" />
        {t("filters.moreFilters")}
        {showMore ? (
          <ChevronUp size="0.75rem" />
        ) : (
          <ChevronDown size="0.75rem" />
        )}
      </button>

      {showMore && (
        <div
          className="fade-up"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(8.75rem, 1fr))",
            gap: "0.5rem",
          }}
        >
          <label className="field" style={{ gap: "0.1875rem", minWidth: 0 }}>
            <span style={fieldLabelStyle}>{t("filters.letter")}</span>
            <select
              className="input"
              style={selectStyle}
              value={value.ltr}
              onChange={(e) => {
                onChange({ ltr: e.target.value });
              }}
            >
              <option value="">{all}</option>
              {CYRILLIC_LETTERS.map((letter) => (
                <option key={letter} value={letter}>
                  {letter}
                </option>
              ))}
            </select>
          </label>
          <FacetSelect
            label={t("filters.category")}
            value={value.category}
            allLabel={all}
            options={facets?.categories ?? []}
            onChange={(v) => {
              onChange({ category: v });
            }}
          />
          <FacetSelect
            label={t("filters.scirank")}
            value={value.scirank}
            allLabel={all}
            options={facets?.sciranks ?? []}
            onChange={(v) => {
              onChange({ scirank: v });
            }}
          />
          <FacetSelect
            label={t("filters.position")}
            value={value.position}
            allLabel={all}
            options={facets?.positions ?? []}
            onChange={(v) => {
              onChange({ position: v });
            }}
          />
        </div>
      )}

      {interests.length > 0 && (
        <div className="flex flex-col" style={{ gap: "0.25rem" }}>
          <span style={fieldLabelStyle}>{t("filters.interests")}</span>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "0.3125rem",
              maxHeight: "4.5rem",
              overflowY: "auto",
            }}
          >
            {interests.map((it) => {
              const active = value.intst === it.value;
              return (
                <button
                  key={it.value}
                  type="button"
                  onClick={() => {
                    onChange({ intst: active ? "" : it.value });
                  }}
                  style={{
                    fontSize: "0.65625rem",
                    padding: "0.125rem 0.5rem",
                    borderRadius: "999px",
                    cursor: "pointer",
                    border: "1px solid var(--border)",
                    color: active ? "var(--accent)" : "var(--fg-2)",
                    background: active
                      ? "color-mix(in srgb, var(--accent) 12%, transparent)"
                      : "var(--bg-2)",
                  }}
                >
                  {it.label}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
