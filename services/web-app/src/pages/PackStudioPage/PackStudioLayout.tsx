import { Outlet } from "react-router";
import { UiVariantContext } from "@shared/ui";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { AppTitlebar } from "@widgets/AppTitlebar";
import { PACK_STUDIO_CHUNK_MARKER } from "./markers";

/** Каркас Студии шаблонов: заголовок приложения, поле раздела, строка состояния. */
export const PackStudioLayout = () => (
  <div
    className="ps-shell ui-console"
    data-testid="pack-studio-layout"
    data-marker={PACK_STUDIO_CHUNK_MARKER}
  >
    <UiVariantContext.Provider value="console">
      <AppTitlebar showVersion={false} />
      <main className="ps-main">
        <Outlet />
      </main>
    </UiVariantContext.Provider>
    <AppStatusBar />
  </div>
);
