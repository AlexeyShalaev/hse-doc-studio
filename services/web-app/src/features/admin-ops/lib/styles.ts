import type { CSSProperties } from "react";

export const CARD: CSSProperties = {
  borderRadius: "var(--r-3)",
  border: "1px solid var(--border)",
  background: "var(--bg-1)",
  boxShadow: "var(--shadow-1)",
};

export const ACTIONS: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  flexWrap: "wrap",
};

export const HINT: CSSProperties = {
  margin: 0,
  fontSize: 11.5,
  lineHeight: 1.5,
  color: "var(--fg-2)",
};
