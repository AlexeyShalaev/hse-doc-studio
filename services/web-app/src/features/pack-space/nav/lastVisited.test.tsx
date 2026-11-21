import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import {
  readLastVersion,
  useRememberVersion,
  writeLastVersion,
} from "./lastVisited";

const Remember = () => {
  useRememberVersion();
  return null;
};

describe("последняя версия шаблона", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(cleanup);

  it("пишется и читается по пространству, паку и шаблону", () => {
    expect(readLastVersion("ws", "p", "t")).toBeNull();
    writeLastVersion("ws", "p", "t", "1.2.3");
    expect(readLastVersion("ws", "p", "t")).toBe("1.2.3");
    expect(readLastVersion("ws", "p", "other")).toBeNull();
    expect(readLastVersion("other", "p", "t")).toBeNull();
  });

  it("повреждённая запись считается отсутствующей", () => {
    window.localStorage.setItem("ps.space.ws", "{не json");
    expect(readLastVersion("ws", "p", "t")).toBeNull();
    window.localStorage.setItem(
      "ps.space.ws",
      JSON.stringify({ ui: { "nav.last.p/t": 5 } }),
    );
    expect(readLastVersion("ws", "p", "t")).toBeNull();
  });

  it("открытая версия запоминается сама", () => {
    renderSpace(<Remember />, `${SPACE_BASE}/2026.1.3/result`);
    expect(readLastVersion("gallery-ws", "hse-cs-sse", "coursework")).toBe(
      "2026.1.3",
    );
  });
});
