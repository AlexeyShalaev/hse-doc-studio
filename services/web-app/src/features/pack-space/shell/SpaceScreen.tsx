import type { ComponentType, ReactNode } from "react";
import { useIsPhoneWidth } from "@shared/lib";
import { SPACE_QUERY } from "@entities/pack-studio";
import { useSpace } from "../context/SpaceContext";
import { useRememberPlace } from "../context/memory";
import { useSpaceNav } from "../context/useSpaceNav";
import {
  ComingSoon,
  DefaultBottomTabs,
  DefaultHeader,
  SpaceTabs,
} from "./DefaultParts";
import { SpaceShell } from "./SpaceShell";
import { SpaceSlotView } from "./SpaceSlotView";
import { spaceSlots } from "./registry";
import type { SpaceSlots, SpaceTabSlot } from "./spaceSlots";

/**
 * Экран пространства: собирает слоты областей по текущей вкладке и отдаёт их каркасу.
 * `slots` и `phone` подменяют реестр и ширину окна (тесты, галерея).
 */
export const SpaceScreen = ({
  slots = spaceSlots,
  phone,
}: {
  slots?: SpaceSlots;
  phone?: boolean;
}) => {
  const { tab, selection, location } = useSpace();
  const nav = useSpaceNav();
  const viewportPhone = useIsPhoneWidth();
  const isPhone = phone ?? viewportPhone;
  useRememberPlace();

  const view = (name: string, component: ComponentType | undefined) => (
    <SpaceSlotView name={name} component={component} />
  );
  const perTab = (name: string, slot: SpaceTabSlot | undefined) => {
    const component = slot?.[tab];
    return component ? view(`${name}.${tab}`, component) : undefined;
  };
  const changesOpen =
    new URLSearchParams(location.search).get(SPACE_QUERY.changes) === "1";
  const orDefault = (
    component: ComponentType | undefined,
    name: string,
    fallback: ReactNode,
  ) => (component ? view(name, component) : fallback);

  return (
    <SpaceShell
      phone={isPhone}
      header={orDefault(slots.header, "header", <DefaultHeader />)}
      actions={
        <>
          {view("changesButton", slots.changesButton)}
          {view("nextStep", slots.nextStep)}
        </>
      }
      contextBar={orDefault(
        slots.contextBar,
        "contextBar",
        isPhone ? undefined : <SpaceTabs />,
      )}
      nav={perTab("nav", slots.nav)}
      mainTop={perTab("mainTop", slots.mainTop)}
      main={perTab("main", slots.main) ?? <ComingSoon />}
      details={perTab("details", slots.details)}
      detailsOpen={selection !== null}
      changes={slots.changes ? view("changes", slots.changes) : undefined}
      changesOpen={changesOpen}
      onSideClose={() => {
        nav.go(changesOpen ? { changes: false } : { sel: null });
      }}
      bottomTabs={orDefault(
        slots.bottomTabs,
        "bottomTabs",
        <DefaultBottomTabs />,
      )}
    />
  );
};
