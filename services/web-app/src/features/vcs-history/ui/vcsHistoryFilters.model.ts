// Filter model for the "recent changes" timeline — kept separate from the
// component so the value exports (constants/helpers) don't trip Fast Refresh.

export type VcsDatePreset = "all" | "today" | "7d" | "30d" | "custom";

export type VcsHistoryFilterState = {
  query: string;
  kind: string; // "all" or a specific commit kind
  preset: VcsDatePreset;
  from: string; // yyyy-mm-dd (custom range)
  to: string; // yyyy-mm-dd (custom range)
};

export type VcsKindOption = { kind: string; label: string; count: number };

export const EMPTY_VCS_FILTERS: VcsHistoryFilterState = {
  query: "",
  kind: "all",
  preset: "all",
  from: "",
  to: "",
};

export const isVcsFiltersActive = (s: VcsHistoryFilterState): boolean =>
  s.query.trim() !== "" ||
  s.kind !== "all" ||
  s.preset !== "all" ||
  s.from !== "" ||
  s.to !== "";
