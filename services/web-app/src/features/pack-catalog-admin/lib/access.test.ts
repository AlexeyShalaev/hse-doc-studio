import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { CatalogSourceSchema } from "@entities/pack-catalog";
import {
  accessComplete,
  accessOf,
  accessUpdate,
  gitSourceRequest,
  updateRequest,
  type GitSourceForm,
} from "./access";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-catalog/fixtures",
);
const load = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8"));

const GIT = CatalogSourceSchema.parse(load("CatalogSource", "git_applied"));
const ARCHIVE = CatalogSourceSchema.parse(
  load("CatalogSource", "archive_failed"),
);

const form = (patch: Partial<GitSourceForm> = {}): GitSourceForm => ({
  url: "https://github.com/acme/packs",
  label: "",
  packsPath: "",
  ref: "",
  access: { kind: "none" },
  insecureHttp: false,
  replaceBuiltin: false,
  track: false,
  ...patch,
});

describe("тело «Добавить источник» git", () => {
  it("минимальное тело: адрес и флаги", () => {
    expect(gitSourceRequest(form())).toEqual({
      url: "https://github.com/acme/packs",
      replace_builtin: false,
      track: false,
    });
  });

  it("как эталон full.json: папка, ref, служебный доступ, отслеживание", () => {
    expect(
      gitSourceRequest(
        form({
          url: " https://git.example.org/acme/packs.git ",
          label: "acme-packs",
          packsPath: "packs",
          ref: "v2026.1.1",
          access: {
            kind: "service",
            serviceAccessId: "9d8c7b6a-5f4e-4d3c-8b2a-190807060504",
          },
          track: true,
        }),
      ),
    ).toEqual(load("CreateGitSourceRequest", "full"));
  });

  it("http без шифрования только по галочке и только для http://", () => {
    expect(
      gitSourceRequest(
        form({ url: "http://git.lan/packs", insecureHttp: true }),
      ).insecure_http,
    ).toBe(true);
    expect(
      gitSourceRequest(form({ insecureHttp: true })).insecure_http,
    ).toBeUndefined();
  });

  it("личный доступ уходит credential_id, незавершённый выбор не готов", () => {
    expect(
      gitSourceRequest(
        form({ access: { kind: "personal", credentialId: "c1" } }),
      ).credential_id,
    ).toBe("c1");
    expect(accessComplete({ kind: "personal", credentialId: null })).toBe(
      false,
    );
    expect(accessComplete({ kind: "none" })).toBe(true);
  });
});

describe("тело «Изменить»", () => {
  const same = {
    label: GIT.label,
    packsPath: GIT.packs_path,
    ref: GIT.ref ?? "",
    access: accessOf(GIT),
    replaceBuiltin: GIT.replace_builtin,
    track: GIT.track,
  };

  it("без правок тело пустое, доступ не отправляется", () => {
    expect(updateRequest(GIT, same)).toEqual({});
    expect(accessUpdate(GIT, accessOf(GIT))).toEqual({});
  });

  it("как эталон ref.json: новый тег без отслеживания", () => {
    expect(
      updateRequest(GIT, { ...same, ref: "v2026.2.0", track: false }),
    ).toEqual(load("UpdateSourceRequest", "ref"));
  });

  it("пустой ref сбрасывает на ветку по умолчанию", () => {
    expect(updateRequest(GIT, { ...same, ref: "  " })).toEqual({ ref: "" });
  });

  it("убранный доступ это clear_access, как в эталоне", () => {
    expect(updateRequest(GIT, { ...same, access: { kind: "none" } })).toEqual(
      load("UpdateSourceRequest", "clear_access"),
    );
  });

  it("у архива нет ref, доступа и отслеживания", () => {
    expect(
      updateRequest(ARCHIVE, {
        label: "Новое имя",
        packsPath: "packs",
        ref: "main",
        access: { kind: "personal", credentialId: "c1" },
        replaceBuiltin: true,
        track: true,
      }),
    ).toEqual({
      label: "Новое имя",
      packs_path: "packs",
      replace_builtin: true,
    });
  });
});
