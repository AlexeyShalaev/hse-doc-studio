import { afterEach, describe, expect, it } from "vitest";
import {
  MAX_AVATARS,
  deviceKind,
  hasDocument,
  pickPeople,
  splitPeople,
  tabSessionId,
} from "./lib/peopleLib";
import { PersonOnlineSchema, ProjectPeopleSchema } from "./model/people.schema";
import { makeLink, makePeople, makePerson, makeServer } from "./testing";

const crowd = (n: number) =>
  Array.from({ length: n }, (_, i) =>
    makePerson({ user_id: `u${String(i)}`, me: i === 0 }),
  );

describe("список людей в проекте", () => {
  it("показывает не больше пяти, остальные счётчиком", () => {
    const { shown, hidden } = splitPeople(crowd(8), 8);
    expect(shown).toHaveLength(MAX_AVATARS);
    expect(hidden).toBe(3);
  });

  it("сервер урезал список до лимита: счётчик берёт общее число", () => {
    const { shown, hidden } = splitPeople(crowd(50), 120);
    expect(shown).toHaveLength(MAX_AVATARS);
    expect(hidden).toBe(115);
  });

  it("свой аватар всегда среди показанных, даже если сервер поставил его не первым", () => {
    const people = [
      ...crowd(6).slice(1),
      makePerson({ user_id: "me", me: true }),
    ];
    const { shown } = splitPeople(people, people.length);
    expect(shown.some((p) => p.me)).toBe(true);
    expect(shown).toHaveLength(MAX_AVATARS);
  });

  it("устройство: веб, Студия или оба, без деталей машины", () => {
    expect(deviceKind({ channels: ["web"] })).toBe("web");
    expect(deviceKind({ channels: ["studio"] })).toBe("studio");
    expect(deviceKind({ channels: ["web", "studio"] })).toBe("both");
  });

  it("к документу ведёт только человек с документом, работающий локально без него", () => {
    expect(hasDocument(makePerson({ doc_id: "tz" }))).toBe(true);
    expect(hasDocument(makePerson({ doc_id: null }))).toBe(false);
    expect(hasDocument(makePerson({ doc_id: "tz", activity: "local" }))).toBe(
      false,
    );
  });

  it("схема строгая: лишнее поле, например путь файла, не принимается", () => {
    const ok = makePerson();
    expect(() => PersonOnlineSchema.parse(ok)).not.toThrow();
    expect(() =>
      PersonOnlineSchema.parse({ ...ok, path: "/Users/anna/диплом" }),
    ).toThrow();
    expect(() => ProjectPeopleSchema.parse(makePeople([ok]))).not.toThrow();
  });

  it("локальная Студия берёт людей из ответа рабочего сервера", () => {
    const people = makePeople([makePerson()]);
    const server = makeServer({
      cloud: { online_window_s: 180, device: null, others: [], people },
    });
    expect(pickPeople(makeLink({ servers: [server] }))).toEqual(people);
    expect(pickPeople(makeLink({ servers: [makeServer()] }))).toBeNull();
    expect(
      pickPeople(
        makeLink({
          servers: [{ ...server, state: "expired" }],
        }),
      ),
    ).toBeNull();
    expect(pickPeople(undefined)).toBeNull();
  });
});

describe("идентификатор вкладки", () => {
  afterEach(() => {
    window.sessionStorage.clear();
  });

  it("не меняется при перезагрузке и подходит под контракт сервера", () => {
    const first = tabSessionId();
    expect(first).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    expect(tabSessionId()).toBe(first);
  });

  it("испорченное значение заменяется годным", () => {
    window.sessionStorage.setItem("hds.presence.session", "x y");
    expect(tabSessionId()).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
  });
});
