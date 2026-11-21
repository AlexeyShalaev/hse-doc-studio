import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import {
  SPACE_QUERY,
  type PackTree,
  type PackTreePack,
  type PackTreeTemplate,
  type PackTreeVersion,
  type PackVersionRef,
  type PackWorkspace,
  type SpaceTab,
} from "@entities/pack-studio";

/**
 * Откуда пространство берёт адрес и куда пишет. В приложении это роутер; галерея состояний и
 * тесты подменяют источник (внутри роутера приложения второй роутер не вложить).
 */
export type SpaceLocation = {
  pathname: string;
  search: string;
  navigate: (to: string, options?: { replace?: boolean }) => void;
};

/** Всё, что экран пространства знает о месте человека. Только чтение; пишут через `useSpaceNav`. */
export type SpaceValue = {
  workspace: PackWorkspace;
  tree: PackTree;
  /** Версия, которую смотрим (имя `versionRef`: `ref` у React зарезервировано). */
  versionRef: PackVersionRef;
  tab: SpaceTab;
  pack: PackTreePack | undefined;
  template: PackTreeTemplate | undefined;
  version: PackTreeVersion | undefined;
  /** Версия выпущена и не меняется (замок). */
  released: boolean;
  /** Выбранный элемент результата, `<раздел>:<id>` (`sel`); `null`: ничего не выбрано. */
  selection: string | null;
  location: SpaceLocation;
};

const Context = createContext<SpaceValue | null>(null);

export type SpaceProviderProps = {
  workspace: PackWorkspace;
  tree: PackTree;
  versionRef: PackVersionRef;
  tab: SpaceTab;
  /** Подмена адреса для галереи и тестов. */
  location?: SpaceLocation;
  children: ReactNode;
};

export const SpaceProvider = ({
  workspace,
  tree,
  versionRef,
  tab,
  location: override,
  children,
}: SpaceProviderProps) => {
  const router = useLocation();
  const navigate = useNavigate();
  const location = useMemo<SpaceLocation>(
    () =>
      override ?? {
        pathname: router.pathname,
        search: router.search,
        navigate: (to, options) => {
          void navigate(to, options);
        },
      },
    [override, router.pathname, router.search, navigate],
  );
  const value = useMemo<SpaceValue>(() => {
    const pack = tree.packs.find((item) => item.id === versionRef.pack);
    const template = pack?.templates.find(
      (item) => item.id === versionRef.template,
    );
    const version = template?.versions.find(
      (item) => item.version === versionRef.version,
    );
    return {
      workspace,
      tree,
      versionRef,
      tab,
      pack,
      template,
      version,
      released: version?.released ?? false,
      selection: new URLSearchParams(location.search).get(SPACE_QUERY.sel),
      location,
    };
  }, [workspace, tree, versionRef, tab, location]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
};

/** Место человека в пространстве. Вне `SpaceProvider` это ошибка разработчика. */
export const useSpace = (): SpaceValue => {
  const value = useContext(Context);
  if (!value) throw new Error("useSpace вне SpaceProvider");
  return value;
};

/** Разбор `sel`: раздел и id (id может содержать двоеточие, делим по первому). */
export const parseSelection = (
  raw: string | null,
): { section: string; id: string } | null => {
  const cut = raw?.indexOf(":") ?? -1;
  if (!raw || cut < 1 || cut === raw.length - 1) return null;
  return { section: raw.slice(0, cut), id: raw.slice(cut + 1) };
};
