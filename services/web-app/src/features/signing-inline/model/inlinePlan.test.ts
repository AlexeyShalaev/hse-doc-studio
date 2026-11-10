import { describe, expect, it } from "vitest";
import type { SigningTask, SigningTaskMe } from "@entities/signing-route";
import { makeSigningTask } from "@entities/signing-route/testing";
import {
  chosenMethod,
  inlinePlan,
  keyOptions,
  pendingSlots,
  type KeyOption,
} from "./inlinePlan";
import { INITIAL_INLINE_UI } from "./types";

const base = makeSigningTask();
const KEY: KeyOption = {
  id: "k1",
  label: "Ключ OpenPGP",
  kind: "openpgp",
  protected: true,
};

const task = (
  me: Partial<SigningTaskMe>,
  doc: Partial<SigningTask["docs"][number]> = {},
): SigningTask =>
  makeSigningTask({
    me: { ...base.me, ...me },
    docs: base.docs.map((d) => ({ ...d, ...doc })),
  });

const allowed = (key: KeyOption | null = KEY): SigningTaskMe["keys"] => ({
  server_keys_allowed: true,
  default_key: key ? { ...key, signer: "Петров П. П." } : null,
});

const plan = (
  t: SigningTask,
  choice: Partial<typeof INITIAL_INLINE_UI> = {},
  identities?: KeyOption[],
) => inlinePlan(t, { ...INITIAL_INLINE_UI, ...choice }, identities);

describe("способ подписи", () => {
  it("берётся способ слота, выбор на странице только из разрешённых", () => {
    const me = {
      ...base.me,
      method: "detached",
      methods: ["image", "detached"],
    };
    expect(chosenMethod(me as SigningTaskMe, null)).toBe("detached");
    expect(chosenMethod(me as SigningTaskMe, "image")).toBe("image");
    expect(chosenMethod(me as SigningTaskMe, "pades")).toBe("detached");
  });

  it("способ слота запрещён точкой: первый разрешённый", () => {
    const me = { ...base.me, method: "pades", methods: ["image", "detached"] };
    expect(chosenMethod(me as SigningTaskMe, null)).toBe("image");
  });

  it("согласующему без слотов блок не нужен", () => {
    expect(
      plan(task({ method: null, methods: [], next_action: "approve" })),
    ).toBeNull();
    expect(plan(task({ next_action: "wait" }))).toBeNull();
  });
});

describe("картинкой", () => {
  const image = (ready: boolean) =>
    task(
      {
        state: "to_approve",
        next_action: "approve",
        method: "image",
        methods: ["image", "detached"],
        image_ready: ready,
        plate: null,
      },
      { frozen: false },
    );

  it("без картинки «Согласовать» ждёт её", () => {
    const p = plan(image(false));
    expect(p).toMatchObject({
      block: "image",
      label: "approve",
      blocker: "image",
      methodChange: null,
      needsSign: false,
    });
    expect(p?.methods).toEqual(["image", "detached"]);
  });

  it("с картинкой одно нажатие", () => {
    expect(plan(image(true))?.blocker).toBeNull();
  });

  it("смена способа уходит в согласие", () => {
    const p = plan(image(true), { method: "detached" });
    expect(p).toMatchObject({
      block: "esign",
      method: "detached",
      methodChange: "detached",
      label: "approve",
      blocker: "plate",
    });
  });
});

describe("ЭП до фиксации", () => {
  it("плашка известна: «Согласовать» без подписи", () => {
    const p = plan(
      task({ state: "to_approve", next_action: "approve" }, { frozen: false }),
    );
    expect(p).toMatchObject({
      block: "esign",
      label: "approve",
      blocker: null,
      needsSign: false,
      canSetPlate: true,
    });
  });

  it("последний, кто меняет видимый слой: ключ Студии заполнит плашку сам", () => {
    const p = plan(
      task(
        { next_action: "approve_and_sign", plate: null, keys: allowed() },
        { frozen: false },
      ),
    );
    expect(p).toMatchObject({
      label: "approve_and_sign",
      way: "studio",
      blocker: null,
      canSetPlate: true,
    });
    expect(p?.key).toEqual(KEY);
  });

  it("готовая подпись: сейчас согласие, подпись после фиксации", () => {
    const p = plan(
      task({ next_action: "approve_and_sign" }, { frozen: false }),
      {
        way: "file",
      },
    );
    expect(p).toMatchObject({
      label: "approve",
      signAfterFreeze: true,
      blocker: null,
    });
  });

  it("готовой подписи нужен сертификат для плашки", () => {
    const p = plan(
      task({ next_action: "approve_and_sign", plate: null }, { frozen: false }),
      { way: "file" },
    );
    expect(p?.blocker).toBe("plate");
  });
});

describe("ЭП после фиксации", () => {
  it("ключи на сервере запрещены: способ выбирает человек, ключа Студии нет", () => {
    const p = plan(base);
    expect(p).toMatchObject({
      frozen: true,
      canSetPlate: false,
      serverKeys: false,
      way: null,
      blocker: "way",
      label: "approve_and_sign",
    });
    expect(p?.ways).toEqual(["cryptopro", "file"]);
    expect(p?.keys).toEqual([]);
  });

  it("КриптоПро не ждёт ничего заранее", () => {
    expect(plan(base, { way: "cryptopro" })?.blocker).toBeNull();
  });

  it("готовая подпись ждёт файл к каждому слоту", () => {
    expect(plan(base, { way: "file" })?.blocker).toBe("files");
    const file = new File(["sig"], "doc.pdf.asc");
    expect(
      plan(base, {
        way: "file",
        files: { "topic_application/supervisor": file },
      })?.blocker,
    ).toBeNull();
  });

  it("ключ Студии: без ключа ждёт его, выбранный ключ побеждает ключ по умолчанию", () => {
    const none = plan(task({ keys: allowed(null) }), {}, []);
    expect(none).toMatchObject({ way: "studio", blocker: "key", key: null });
    const other: KeyOption = { ...KEY, id: "k2", protected: false };
    const picked = plan(task({ keys: allowed() }), { identityId: "k2" }, [
      KEY,
      other,
    ]);
    expect(picked?.key).toEqual(other);
    expect(picked?.keys.map((k) => k.id)).toEqual(["k1", "k2"]);
  });

  it("«Подписать» итоговый PDF: способ уже не меняется", () => {
    const p = plan(
      task({
        state: "to_sign",
        next_action: "sign",
        methods: ["image", "detached"],
        keys: allowed(),
      }),
      { method: "image" },
    );
    expect(p).toMatchObject({
      label: "sign",
      method: "detached",
      methods: [],
      blocker: null,
    });
  });

  it("ЭП в PDF ставит только ключ Студии", () => {
    const pades: Partial<SigningTaskMe> = {
      method: "pades",
      methods: ["pades"],
    };
    expect(plan(task({ ...pades, keys: allowed() }))?.ways).toEqual(["studio"]);
    const forbidden = plan(task(pades));
    expect(forbidden?.ways).toEqual([]);
    expect(forbidden?.blocker).toBe("way");
  });
});

describe("ключи и слоты", () => {
  it("ключ по умолчанию первым, запись из списка точнее сводки задачи", () => {
    const summary = { ...KEY, protected: false, signer: "Петров П. П." };
    expect(keyOptions(summary, undefined)).toEqual([
      { ...KEY, protected: false },
    ]);
    const other: KeyOption = { ...KEY, id: "k2" };
    expect(keyOptions(summary, [other, KEY])).toEqual([KEY, other]);
    expect(keyOptions(null, [other])).toEqual([other]);
  });

  it("ждут подписи только свои неподписанные слоты", () => {
    expect(pendingSlots(base)).toEqual([
      {
        key: "topic_application/supervisor",
        docId: "topic_application",
        slotId: "supervisor",
        docName: base.docs[0]?.name,
        frozen: true,
        pdfUrl: base.docs[0]?.pdf_url,
      },
    ]);
    const signed = makeSigningTask({
      docs: base.docs.map((d) => ({
        ...d,
        mine: d.mine.map((s) => ({ ...s, status: "signed" as const })),
      })),
    });
    expect(pendingSlots(signed)).toEqual([]);
  });

  it("документ без отпечатка (без изменений в новой версии) действие не трогает", () => {
    const kept = makeSigningTask({
      docs: base.docs.map((d) => ({ ...d, token: null })),
    });
    expect(pendingSlots(kept)).toEqual([]);
  });
});
