import { describe, expect, it } from "vitest";
import { CLONE_PATH, gitClonePath, readCloneTarget } from "./syncPaths";

describe("адрес мастера клонирования", () => {
  it("без адреса репозитория ведёт в пустой мастер", () => {
    expect(gitClonePath()).toBe(CLONE_PATH);
    expect(gitClonePath(null)).toBe("/wizard?mode=clone");
  });

  it("с адресом и доступом передаёт их в строке запроса и читает обратно", () => {
    const target = {
      url: "https://github.com/hse-team/paper.git",
      credentialId: "cred-1",
    };
    const path = gitClonePath(target);
    expect(path).toContain("mode=clone");
    const query = new URLSearchParams(path.split("?")[1]);
    expect(readCloneTarget(query)).toEqual(target);
  });

  it("без сохранённого доступа не добавляет его", () => {
    const path = gitClonePath({
      url: "git@github.com:hse-team/paper.git",
      credentialId: null,
    });
    expect(path).not.toContain("credential");
    expect(readCloneTarget(new URLSearchParams(path.split("?")[1]))).toEqual({
      url: "git@github.com:hse-team/paper.git",
      credentialId: null,
    });
  });

  it("адрес со спецсимволами не ломает строку запроса", () => {
    const target = { url: "https://host/a?b=1&c=2#x", credentialId: null };
    const query = new URLSearchParams(gitClonePath(target).split("?")[1]);
    expect(readCloneTarget(query)?.url).toBe(target.url);
  });

  it("пустой или отсутствующий адрес даёт null", () => {
    expect(readCloneTarget(new URLSearchParams("mode=clone"))).toBeNull();
    expect(
      readCloneTarget(new URLSearchParams("mode=clone&url=%20")),
    ).toBeNull();
  });
});
