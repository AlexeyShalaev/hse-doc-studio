import { RouterProvider } from "react-router";
import { StaleBuildBanner } from "@widgets/StaleBuildBanner";
import { Providers } from "./providers";
import { router } from "./router";

export const App = () => (
  <Providers>
    <RouterProvider router={router} />
    <StaleBuildBanner />
  </Providers>
);
