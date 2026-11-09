import { Suspense, lazy } from "react";
import { Spinner } from "@shared/ui";
import type { SigningRouteEditorProps } from "./SigningRouteEditor";

// Экран — отдельный чанк (SigningRouteEditor-*.js): его код грузится, только когда автор
// открывает отправку на подписание.
const Editor = lazy(() =>
  import("./SigningRouteEditor").then((m) => ({
    default: m.SigningRouteEditor,
  })),
);

export const SigningRouteEditorLazy = (props: SigningRouteEditorProps) => (
  <Suspense
    fallback={
      <div className="flex flex-1 items-center justify-center">
        <Spinner />
      </div>
    }
  >
    <Editor {...props} />
  </Suspense>
);
