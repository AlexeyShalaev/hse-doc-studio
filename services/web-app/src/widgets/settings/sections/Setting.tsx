// `anchorId` makes a setting a scroll target for the content search — clicking a
// search result jumps to this element and flashes it (see SettingsPage).
const anchorClass = (anchorId: string | undefined, base: string): string =>
  anchorId ? `${base} settings-anchor` : base;

export type SettingHeadProps = {
  title: string;
  sub?: string;
  anchorId?: string;
};

export const SettingHead = ({ title, sub, anchorId }: SettingHeadProps) => (
  <div
    id={anchorId}
    className={anchorClass(anchorId, "flex flex-col")}
    style={{ gap: 4, marginBottom: 4 }}
  >
    <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{title}</h4>
    {sub && (
      <p style={{ margin: 0, color: "var(--fg-2)", fontSize: 12 }}>{sub}</p>
    )}
  </div>
);

export type SettingProps = {
  label: string;
  hint?: string;
  anchorId?: string;
  children: React.ReactNode;
};

export const Setting = ({ label, hint, anchorId, children }: SettingProps) => (
  <div
    id={anchorId}
    className={anchorClass(anchorId, "flex flex-col")}
    style={{
      gap: 8,
      paddingBottom: 14,
      borderBottom: "1px dashed var(--border)",
    }}
  >
    <div className="flex items-center justify-between" style={{ gap: 12 }}>
      <div className="flex flex-col" style={{ gap: 2 }}>
        <label style={{ fontSize: 12, fontWeight: 500 }}>{label}</label>
        {hint && <span className="hint">{hint}</span>}
      </div>
      <div style={{ maxWidth: "60%" }}>{children}</div>
    </div>
  </div>
);
