import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { RoutePersonOption } from "@entities/signing-route";
import { makeRouteParticipant } from "@entities/signing-route/testing";
import { ParticipantRow, type ParticipantRowProps } from "./ParticipantRow";

const PETROV: RoutePersonOption = {
  kind: "member",
  id: "u_petrov",
  name: "Петров П. П.",
};
const INVITED: RoutePersonOption = {
  kind: "invitation",
  id: "inv_1",
  name: "k***@hse.ru",
};

const mount = (props: Partial<ParticipantRowProps>) => {
  const onPick = vi.fn();
  const onInvite = vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <ParticipantRow
        participant={makeRouteParticipant({
          id: "srp_supervisor",
          persona: "supervisor",
          user_id: null,
          name: null,
          membership: "missing",
          state: "waiting",
          next_action: "wait",
        })}
        preview={undefined}
        personaLabel="Научный руководитель"
        isMe={false}
        editable
        busy={false}
        options={[]}
        registrationClosed={false}
        menu={[]}
        onDragStart={() => undefined}
        onDragEnd={() => undefined}
        onInvite={onInvite}
        onPick={onPick}
        {...props}
      />
    </I18nextProvider>,
  );
  return { onPick, onInvite };
};

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

describe("человек шага: выбор из кандидатов", () => {
  it("нет в проекте, но выбрать есть из кого: список и «Пригласить» рядом", async () => {
    const { onPick, onInvite } = mount({ options: [PETROV, INVITED] });
    const pick = screen.getByTestId("route-pick-supervisor");
    expect(pick).toHaveAccessibleName("Кто подписывает: Научный руководитель");
    expect(
      within(pick)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Выбрать человека", "Петров П. П.", "k***@hse.ru (приглашение отправлено)"]);
    const user = userEvent.setup();
    await user.selectOptions(pick, "invitation:inv_1");
    expect(onPick).toHaveBeenCalledWith(INVITED);
    await user.click(screen.getByTestId("route-invite"));
    expect(onInvite).toHaveBeenCalled();
  });

  it("нет в проекте и выбрать не из кого: только «Пригласить»", () => {
    mount({ options: [] });
    expect(screen.queryByTestId("route-pick-supervisor")).toBeNull();
    expect(screen.getByTestId("route-invite")).toBeInTheDocument();
    expect(screen.getByText("Человек не назначен")).toBeInTheDocument();
  });

  it("единственный кандидат уже стоит: выбирать не из кого", () => {
    mount({
      participant: makeRouteParticipant({
        persona: "supervisor",
        user_id: PETROV.id,
        name: PETROV.name,
      }),
      options: [PETROV],
    });
    expect(screen.queryByTestId("route-pick-supervisor")).toBeNull();
    expect(screen.queryByTestId("route-invite")).toBeNull();
  });

  it("приглашение без имени: «Приглашённый», а не «человек не назначен»", () => {
    mount({
      participant: makeRouteParticipant({
        persona: "supervisor",
        user_id: null,
        invitation_id: "inv_2",
        name: null,
        membership: "invited",
      }),
    });
    expect(screen.getByText("Приглашённый")).toBeInTheDocument();
    expect(screen.queryByText("Человек не назначен")).toBeNull();
  });

  it("маршрут отправлен: выбора нет", () => {
    mount({ editable: false, options: [PETROV, INVITED] });
    expect(screen.queryByTestId("route-pick-supervisor")).toBeNull();
    expect(screen.queryByTestId("route-invite")).toBeNull();
  });
});
