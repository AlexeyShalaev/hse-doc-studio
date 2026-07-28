import { RouterProvider } from "react-router";
import { Providers } from "./providers";
import { router } from "./router";

export const App = () => (
  <Providers>
    <RouterProvider router={router} />
  </Providers>
);
