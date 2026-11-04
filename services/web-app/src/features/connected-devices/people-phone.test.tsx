import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { installViewport } from "@shared/lib/viewport/testing";
import { makePeople, makePerson } from "@entities/connected-device/testing";
import { PeopleOnline } from "./ui/PeopleOnline";

const crowd = makePeople(
  [
    makePerson({ user_id: "me", me: true, name: "Анна", initials: "АП" }),
    makePerson({ user_id: "b", name: "Борис", initials: "БС" }),
    makePerson({ user_id: "c", name: "Виктор", initials: "ВС" }),
    makePerson({ user_id: "d", name: "Галина", initials: "ГИ" }),
  ],
  4,
);

describe("PeopleOnline on a phone", () => {
  let viewport: ReturnType<typeof installViewport> | undefined;
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    viewport?.restore();
    viewport = undefined;
  });

  it("is one 40 px button with two avatars and the rest as a count", () => {
    viewport = installViewport(390);
    render(<PeopleOnline people={crowd} docName={() => null} />);
    const group = screen.getByTestId("project-people");
    expect(group.tagName).toBe("BUTTON");
    expect(group.querySelectorAll(".pp-avatar")).toHaveLength(2);
    expect(group).toHaveTextContent("+2");
    expect(screen.queryByTestId("people-more")).not.toBeInTheDocument();
  });

  it("opens the list of people as a sheet, with a row per person", async () => {
    viewport = installViewport(360);
    render(<PeopleOnline people={crowd} docName={() => null} />);
    await userEvent.setup().click(screen.getByTestId("project-people"));
    const list = screen.getByTestId("people-list");
    expect(within(list).getAllByTestId("people-row")).toHaveLength(4);
    expect(list.closest("[data-form]")).toHaveAttribute("data-form", "sheet");
  });

  it("keeps the desktop strip of avatar buttons", () => {
    viewport = installViewport(1360);
    render(<PeopleOnline people={crowd} docName={() => null} />);
    expect(screen.getByTestId("project-people").tagName).toBe("DIV");
    expect(screen.getByTestId("people-more")).toBeInTheDocument();
  });

  it("draws nothing while the viewer is alone", () => {
    viewport = installViewport(390);
    render(
      <PeopleOnline
        people={makePeople([makePerson({ me: true })])}
        docName={() => null}
      />,
    );
    expect(screen.queryByTestId("project-people")).not.toBeInTheDocument();
  });
});
