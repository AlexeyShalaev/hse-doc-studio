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
  fontSize: 10.5,
  color: "var(--fg-3)",
};
const selectStyle: React.CSSProperties = {
  fontSize: 12,
  padding: "6px 7px",
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
  <label className="field" style={{ gap: 3, minWidth: 0 }}>
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
    <div className="flex flex-col" style={{ gap: 10 }}>
      {/* Campus — a segmented pill row (4 fixed campuses). */}
      <div className="flex flex-col" style={{ gap: 4 }}>
        <span style={fieldLabelStyle}>{t("filters.campus")}</span>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
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
                  fontSize: 12,
                  padding: "5px 12px",
                  borderRadius: 999,
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
      <label className="field" style={{ gap: 3, minWidth: 0 }}>
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
        style={{ alignSelf: "flex-start", gap: 6 }}
      >
        <SlidersHorizontal size={12} />
        {t("filters.moreFilters")}
        {showMore ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {showMore && (
        <div
          className="fade-up"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: 8,
          }}
        >
          <label className="field" style={{ gap: 3, minWidth: 0 }}>
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
        <div className="flex flex-col" style={{ gap: 4 }}>
          <span style={fieldLabelStyle}>{t("filters.interests")}</span>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 5,
              maxHeight: 72,
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
                    fontSize: 10.5,
                    padding: "2px 8px",
                    borderRadius: 999,
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
