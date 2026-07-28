import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ExternalLink } from "lucide-react";

import { useHsePersonDetail, type HsePersonSummary } from "../api";

export type HsePersonRowProps = {
  person: HsePersonSummary;
  // The scroll container — lazy detail fires only when the row is visible in it.
  rootRef: React.RefObject<HTMLDivElement | null>;
  onPick: (id: string) => void;
  picking: boolean;
};

const initials = (name: string): string =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

export const HsePersonRow = ({
  person,
  rootRef,
  onPick,
  picking,
}: HsePersonRowProps) => {
  const { t } = useTranslation("hsePerson");
  const rowRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);
  const [hovered, setHovered] = useState(false);

  useEffect(() => {
    const node = rowRef.current;
    if (node === null || visible) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setVisible(true);
      },
      { root: rootRef.current, rootMargin: "120px" },
    );
    observer.observe(node);
    return () => {
      observer.disconnect();
    };
  }, [rootRef, visible]);

  const { data: detail } = useHsePersonDetail(person.id, visible);

  const subline =
    detail !== undefined
      ? [detail.position, detail.department].filter(Boolean).join(" · ")
      : person.affiliation;

  return (
    <div
      ref={rowRef}
      onMouseEnter={() => {
        setHovered(true);
      }}
      onMouseLeave={() => {
        setHovered(false);
      }}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        borderRadius: 8,
        border: "1px solid var(--border)",
        background: hovered ? "var(--bg-3)" : "var(--bg-2)",
        paddingRight: 6,
      }}
    >
      <button
        type="button"
        onClick={() => {
          onPick(person.id);
        }}
        disabled={picking}
        title={t("results.pickHint")}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          flex: 1,
          minWidth: 0,
          textAlign: "left",
          padding: "8px 4px 8px 10px",
          border: "none",
          background: "transparent",
          cursor: picking ? "progress" : "pointer",
        }}
      >
        {visible && !imgFailed ? (
          <img
            src={person.photo_url}
            alt=""
            loading="lazy"
            width={34}
            height={34}
            onError={() => {
              setImgFailed(true);
            }}
            style={{
              width: 34,
              height: 34,
              borderRadius: "50%",
              objectFit: "cover",
              flexShrink: 0,
            }}
          />
        ) : (
          <span
            aria-hidden
            style={{
              width: 34,
              height: 34,
              borderRadius: "50%",
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 12,
              fontWeight: 600,
              color: "var(--fg-2)",
              background: "var(--bg-3)",
            }}
          >
            {initials(person.full_name)}
          </span>
        )}
        <span style={{ flex: 1, minWidth: 0 }}>
          <span
            style={{
              display: "block",
              fontSize: 13,
              fontWeight: 500,
              color: "var(--fg-0)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {person.full_name}
          </span>
          <span
            style={{
              display: "block",
              fontSize: 11,
              color: "var(--fg-3)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {subline || t("results.noPosition")}
          </span>
        </span>
        {detail?.degree ? (
          <span
            style={{
              flexShrink: 0,
              fontSize: 10,
              padding: "2px 6px",
              borderRadius: 4,
              color: "var(--accent)",
              background: "color-mix(in srgb, var(--accent) 12%, transparent)",
            }}
          >
            {detail.degree}
          </span>
        ) : null}
      </button>
      <a
        href={person.profile_url}
        target="_blank"
        rel="noopener noreferrer"
        className="icon-btn sm"
        title={t("results.openProfile")}
        aria-label={t("results.openProfile")}
        style={{ flexShrink: 0, color: "var(--fg-3)" }}
      >
        <ExternalLink size={14} />
      </a>
    </div>
  );
};
