import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";

import { Modal } from "@shared/ui";

import {
  hsePersonDetailQuery,
  useHseFacets,
  useHsePersonSearch,
  type HsePersonSearchParams,
} from "../api";
import {
  toPersonFields,
  useDebouncedValue,
  type HsePersonFields,
} from "../lib";
import {
  HsePersonFilters,
  type HsePersonFilterState,
} from "./HsePersonFilters";
import { HsePersonRow } from "./HsePersonRow";

export type HsePersonLookupModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (fields: HsePersonFields) => void;
  initialQuery?: string;
};

const MIN_QUERY = 2;
const SEARCH_LIMIT = 40;
const DEBOUNCE_MS = 350;

const emptyFilters = (): HsePersonFilterState => ({
  campus: "moscow",
  udept: "",
  ltr: "",
  category: "",
  scirank: "",
  position: "",
  intst: "",
});

export const HsePersonLookupModal = ({
  isOpen,
  onClose,
  onSelect,
  initialQuery = "",
}: HsePersonLookupModalProps) => {
  const { t } = useTranslation("hsePerson");
  const queryClient = useQueryClient();
  const scrollRef = useRef<HTMLDivElement>(null);

  const [query, setQuery] = useState(initialQuery);
  const [filters, setFilters] = useState<HsePersonFilterState>(emptyFilters);
  const [pickingId, setPickingId] = useState<string | null>(null);

  const debouncedQuery = useDebouncedValue(query.trim(), DEBOUNCE_MS);
  const hasFacet =
    filters.ltr !== "" ||
    filters.udept !== "" ||
    filters.category !== "" ||
    filters.scirank !== "" ||
    filters.position !== "" ||
    filters.intst !== "";
  const canSearch = debouncedQuery.length >= MIN_QUERY || hasFacet;

  const facetsQuery = useHseFacets(filters.campus, isOpen);
  const params: HsePersonSearchParams = {
    q: debouncedQuery,
    campus: filters.campus,
    udept: filters.udept,
    ltr: filters.ltr,
    category: filters.category,
    scirank: filters.scirank,
    position: filters.position,
    intst: filters.intst,
    limit: SEARCH_LIMIT,
  };
  const searchQuery = useHsePersonSearch(params, isOpen && canSearch);

  const handlePick = async (id: string) => {
    setPickingId(id);
    try {
      const detail = await queryClient.fetchQuery(hsePersonDetailQuery(id));
      onSelect(toPersonFields(detail));
      onClose();
    } catch {
      // The global query-error interceptor already toasts network/parse errors.
      setPickingId(null);
    }
  };

  const persons = searchQuery.data?.persons ?? [];

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("title")}
      description={t("description")}
      width={780}
    >
      <div className="flex flex-col" style={{ gap: 12 }}>
        <div className="field" style={{ gap: 4 }}>
          <div style={{ position: "relative" }}>
            <Search
              size={16}
              style={{
                position: "absolute",
                left: 12,
                top: "50%",
                transform: "translateY(-50%)",
                color: "var(--fg-3)",
                pointerEvents: "none",
              }}
            />
            <input
              className="input"
              autoFocus
              value={query}
              placeholder={t("search.placeholder")}
              onChange={(e) => {
                setQuery(e.target.value);
              }}
              style={{
                paddingLeft: 38,
                paddingTop: 10,
                paddingBottom: 10,
                fontSize: 14,
                width: "100%",
              }}
            />
          </div>
        </div>

        <HsePersonFilters
          facets={facetsQuery.data}
          interests={searchQuery.data?.interests ?? []}
          value={filters}
          onChange={(patch) => {
            setFilters((prev) => ({ ...prev, ...patch }));
          }}
        />

        {canSearch && persons.length > 0 && (
          <div style={{ fontSize: 11, color: "var(--fg-3)" }}>
            {t("results.count", { count: persons.length })}
          </div>
        )}

        <div
          ref={scrollRef}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 6,
            maxHeight: "48vh",
            overflowY: "auto",
            minHeight: 160,
          }}
        >
          {!canSearch ? (
            <p
              className="hint"
              style={{ margin: "auto 0", textAlign: "center" }}
            >
              {t("results.startHint", { min: MIN_QUERY })}
            </p>
          ) : searchQuery.isError ? (
            <p
              className="hint"
              style={{ margin: "auto 0", textAlign: "center" }}
            >
              {t("results.error")}
            </p>
          ) : searchQuery.isLoading ? (
            <p
              className="hint"
              style={{ margin: "auto 0", textAlign: "center" }}
            >
              {t("results.loading")}
            </p>
          ) : persons.length === 0 ? (
            <p
              className="hint"
              style={{ margin: "auto 0", textAlign: "center" }}
            >
              {t("results.empty")}
            </p>
          ) : (
            persons.map((person) => (
              <HsePersonRow
                key={person.id}
                person={person}
                rootRef={scrollRef}
                onPick={(id) => {
                  void handlePick(id);
                }}
                picking={pickingId !== null}
              />
            ))
          )}
        </div>

        <p className="hint" style={{ margin: 0, fontSize: 10.5 }}>
          {t("results.source")}
        </p>
      </div>
    </Modal>
  );
};
