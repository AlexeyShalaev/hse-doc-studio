import { LocalRuntimePanel } from "@features/manage-local-runtime";

// The local-runtime panel carries its own header + description, so this section
// is a thin wrapper that hosts it as a standalone settings page. The anchor lets
// the settings content search jump here.
export const LocalModelsSection = () => (
  <div id="local-models" className="settings-anchor">
    <LocalRuntimePanel />
  </div>
);
