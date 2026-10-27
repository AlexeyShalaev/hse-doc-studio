import { create } from "zustand";
import { persist } from "zustand/middleware";

// Путь установки сервера (https://host/gitlab → /gitlab), который человек указал
// для хоста. Нужен только для ссылок на страницы сервера, это удобство одного
// компьютера: на сервер он не уходит.
type InstancePathState = {
  paths: Record<string, string>;
  setPath: (host: string, path: string) => void;
};

export const useInstancePathStore = create<InstancePathState>()(
  persist(
    (set) => ({
      paths: {},
      setPath: (host, path) => {
        set((state) => {
          const key = host.toLowerCase();
          const clean = path.trim().replace(/^\/+|\/+$/g, "");
          const rest = Object.fromEntries(
            Object.entries(state.paths).filter(([name]) => name !== key),
          );
          return { paths: clean === "" ? rest : { ...rest, [key]: clean } };
        });
      },
    }),
    { name: "hse-studio.gitInstancePath" },
  ),
);
