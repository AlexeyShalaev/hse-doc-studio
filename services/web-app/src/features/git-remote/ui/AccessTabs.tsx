import { useEffect, useRef, type KeyboardEvent } from "react";
import {
  Globe,
  KeyRound,
  KeySquare,
  Lock,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AccessMethod } from "../model/useRemoteAuth";

export type AccessTabsProps = {
  methods: readonly AccessMethod[];
  value: AccessMethod;
  onChange: (next: AccessMethod) => void;
  /** Префикс id: вкладка `<id>-tab-<способ>`, панель `<id>-panel`. */
  id: string;
};

const ICONS: Record<AccessMethod, LucideIcon> = {
  pat: Lock,
  ssh: KeyRound,
  deploy: KeySquare,
  none: Globe,
};

// Способы доступа как вкладки: у каждого короткое название и одна строка о том,
// чем он хорош. Стрелки переключают вкладки, как в обычном ARIA-списке вкладок.
export const AccessTabs = ({
  methods,
  value,
  onChange,
  id,
}: AccessTabsProps) => {
  const { t } = useTranslation("gitAccess");
  const refs = useRef(new Map<AccessMethod, HTMLButtonElement>());
  // Фокус остаётся на вкладке после стрелки, даже если новая панель сама тянет
  // его к полю ввода (поле токена в фокусе при открытии).
  const focusAfter = useRef<AccessMethod | null>(null);
  useEffect(() => {
    if (focusAfter.current === value) {
      refs.current.get(value)?.focus();
      focusAfter.current = null;
    }
  }, [value]);

  const move = (
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ): void => {
    const last = methods.length - 1;
    let next: number;
    if (event.key === "ArrowRight" || event.key === "ArrowDown")
      next = index === last ? 0 : index + 1;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp")
      next = index === 0 ? last : index - 1;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = last;
    else return;
    event.preventDefault();
    const target = methods[next];
    if (target === undefined) return;
    focusAfter.current = target;
    onChange(target);
    refs.current.get(target)?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label={t("method.label")}
      data-testid="access-tabs"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(128px, 1fr))",
        gap: 6,
      }}
    >
      {methods.map((method, index) => {
        const active = method === value;
        const Icon = ICONS[method];
        return (
          <button
            key={method}
            ref={(node) => {
              if (node) refs.current.set(method, node);
              else refs.current.delete(method);
            }}
            type="button"
            role="tab"
            id={`${id}-tab-${method}`}
            aria-selected={active}
            aria-controls={`${id}-panel`}
            tabIndex={active ? 0 : -1}
            data-testid={`access-tab-${method}`}
            className="flex flex-col items-start"
            style={{
              gap: 3,
              padding: "8px 10px",
              textAlign: "left",
              borderRadius: "var(--r-2)",
              border: `1px solid ${active ? "var(--accent-line)" : "var(--border)"}`,
              background: active ? "var(--accent-soft)" : "var(--bg-1)",
              color: "var(--fg-0)",
              cursor: "pointer",
              minWidth: 0,
            }}
            onClick={() => {
              onChange(method);
            }}
            onKeyDown={(event) => {
              move(event, index);
            }}
          >
            <span
              className="flex items-center"
              style={{
                gap: 6,
                fontSize: 12.5,
                fontWeight: 600,
                color: active ? "var(--accent)" : "var(--fg-0)",
              }}
            >
              <Icon size={13} aria-hidden="true" />
              {t(`method.${method}`)}
            </span>
            <span className="dim" style={{ fontSize: 11, lineHeight: 1.35 }}>
              {t(`method.caption.${method}`)}
            </span>
          </button>
        );
      })}
    </div>
  );
};
