import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AIProviderSource } from "@entities/ai-provider";

export type ModelProviderGroup = {
  providerId: string;
  providerName: string;
  models: string[];
  /**
   * Откуда провайдер; только в серверном режиме (см. toModelGroups). Без него
   * список без групп, как раньше (локальный режим).
   */
  source?: AIProviderSource | undefined;
  /** Почему модели недоступны (раннер не в сети, на паузе); null: доступны. */
  unavailable?: string | null | undefined;
};

const SOURCES: readonly AIProviderSource[] = ["own", "org", "instance"];

type ModelPickerProps = {
  groups: ModelProviderGroup[];
  selectedProviderId: string;
  selectedModel: string;
  disabled?: boolean;
  /** Увеличьте число, чтобы открыть выбор снаружи (кнопка «Выбрать модель» у ошибки). */
  openRequest?: number;
  onSelect: (providerId: string, model: string) => void;
};

type ModelRow = {
  providerId: string;
  providerName: string;
  model: string;
  unavailable: string | null;
};

type Rect = {
  left: number;
  top: number;
  transform: string;
};

// How many models stay visible before the rest collapse under "Другие модели".
const PRIMARY_LIMIT = 6;
const MENU_WIDTH = 300;

/**
 * Copilot-style model picker: a compact pill showing the current model, opening
 * a searchable popover with a short primary list and a collapsible "Другие
 * модели" section for the long tail (extra providers / many models). Each row
 * shows the model on the left and its provider on the right.
 */
export const ModelPicker = ({
  groups,
  selectedProviderId,
  selectedModel,
  disabled = false,
  openRequest = 0,
  onSelect,
}: ModelPickerProps) => {
  const { t } = useTranslation("agentChat");
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [otherOpen, setOtherOpen] = useState(false);
  const [rect, setRect] = useState<Rect | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const allRows: ModelRow[] = groups.flatMap((group) =>
    group.models.map((model) => ({
      providerId: group.providerId,
      providerName: group.providerName,
      model,
      unavailable: group.unavailable ?? null,
    })),
  );
  // Серверный режим: модели по источникам «мои, организации, установки».
  const grouped = groups.some((group) => group.source !== undefined);

  // Запрос открыть выбор снаружи: новое число, ещё не обработанное.
  const [handledRequest, setHandledRequest] = useState(0);
  if (openRequest !== handledRequest) {
    setHandledRequest(openRequest);
    if (openRequest > 0 && !disabled) setOpen(true);
  }

  // Primary = the active provider's models (capped); everything else collapses.
  const primaryProviderId =
    selectedProviderId !== ""
      ? selectedProviderId
      : (groups[0]?.providerId ?? "");
  const primaryAll = allRows.filter((r) => r.providerId === primaryProviderId);
  const overflow = primaryAll.length > PRIMARY_LIMIT;
  const primaryRows = overflow
    ? primaryAll.slice(0, PRIMARY_LIMIT)
    : primaryAll;
  const otherRows = [
    ...(overflow ? primaryAll.slice(PRIMARY_LIMIT) : []),
    ...allRows.filter((r) => r.providerId !== primaryProviderId),
  ];

  const q = query.trim().toLowerCase();
  const filtered = q
    ? allRows.filter(
        (r) =>
          r.model.toLowerCase().includes(q) ||
          r.providerName.toLowerCase().includes(q),
      )
    : null;

  const triggerLabel = selectedModel || t("model.trigger");
  const activeProviderName =
    primaryAll[0]?.providerName ?? groups[0]?.providerName ?? "";

  const place = () => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    // Align the (wider) menu's right edge to the trigger, opening upward.
    setRect({
      left: r.right - MENU_WIDTH,
      top: r.top - 6,
      transform: "translateY(-100%)",
    });
  };

  useLayoutEffect(() => {
    if (open) place();
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const reposition = () => {
      place();
    };
    const onPointerDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        triggerRef.current?.contains(target) ||
        panelRef.current?.contains(target)
      )
        return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const handlePick = (row: ModelRow) => {
    if (row.unavailable) return;
    onSelect(row.providerId, row.model);
    setOpen(false);
    setQuery("");
  };

  const renderRow = (row: ModelRow) => {
    const isActive =
      row.providerId === selectedProviderId && row.model === selectedModel;
    return (
      <button
        key={`${row.providerId}:::${row.model}`}
        type="button"
        className="modelpick-item"
        disabled={row.unavailable !== null}
        aria-disabled={row.unavailable !== null}
        title={
          row.unavailable
            ? t("model.unavailable", { reason: row.unavailable })
            : undefined
        }
        style={
          row.unavailable ? { opacity: 0.55, cursor: "not-allowed" } : undefined
        }
        onClick={() => {
          handlePick(row);
        }}
      >
        <Check
          size={13}
          className="combo-check"
          style={{ opacity: isActive ? 1 : 0 }}
        />
        <span className="modelpick-name truncate">{row.model}</span>
        <span className="modelpick-provider truncate">
          {row.unavailable ?? row.providerName}
        </span>
      </button>
    );
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        className="agent-composer-modelbtn"
        title={
          selectedModel
            ? t("model.titleWithProvider", {
                model: selectedModel,
                provider: activeProviderName,
              })
            : t("model.selectModel")
        }
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => {
          if (!disabled) setOpen((o) => !o);
        }}
      >
        <span className="truncate">{triggerLabel}</span>
        <ChevronDown
          size={13}
          style={{ flexShrink: 0, color: "var(--fg-2)" }}
        />
      </button>

      {open &&
        rect &&
        createPortal(
          <div
            ref={panelRef}
            className="combo-menu modelpick-menu"
            style={{
              position: "fixed",
              left: Math.max(8, rect.left),
              top: rect.top,
              width: MENU_WIDTH,
              transform: rect.transform,
              zIndex: 200,
            }}
          >
            <input
              className="combo-input"
              placeholder={t("model.searchPlaceholder")}
              autoFocus
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
              }}
            />
            <div className="combo-list modelpick-list">
              {filtered ? (
                filtered.length === 0 ? (
                  <div className="combo-empty">{t("model.notFound")}</div>
                ) : (
                  filtered.map(renderRow)
                )
              ) : grouped ? (
                <>
                  <div
                    className="combo-empty"
                    style={{ textAlign: "left", fontSize: 11 }}
                    data-testid="model-picker-default-order"
                  >
                    {t("model.defaultOrder")}
                  </div>
                  {SOURCES.map((source) => {
                    const rows = groups
                      .filter((g) => g.source === source)
                      .flatMap((g) =>
                        allRows.filter((r) => r.providerId === g.providerId),
                      );
                    // Пустая группа (организаций пока нет) не показывается.
                    if (rows.length === 0) return null;
                    return (
                      <div
                        key={source}
                        role="group"
                        aria-label={t(`model.group.${source}`)}
                        data-testid={`model-picker-group-${source}`}
                      >
                        <div
                          className="dim"
                          style={{
                            padding: "6px 10px 2px",
                            fontSize: 10.5,
                            textTransform: "uppercase",
                            letterSpacing: 0.4,
                          }}
                        >
                          {t(`model.group.${source}`)}
                        </div>
                        {rows.map(renderRow)}
                      </div>
                    );
                  })}
                </>
              ) : (
                <>
                  {primaryRows.length === 0 && (
                    <div className="combo-empty">{t("model.noModels")}</div>
                  )}
                  {primaryRows.map(renderRow)}
                  {otherRows.length > 0 && (
                    <>
                      <button
                        type="button"
                        className="modelpick-more"
                        onClick={() => {
                          setOtherOpen((v) => !v);
                        }}
                      >
                        {otherOpen ? (
                          <ChevronDown size={13} />
                        ) : (
                          <ChevronRight size={13} />
                        )}
                        <span>{t("model.otherModels")}</span>
                        <span className="dim modelpick-more-count">
                          {otherRows.length}
                        </span>
                      </button>
                      {otherOpen && otherRows.map(renderRow)}
                    </>
                  )}
                </>
              )}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
};
