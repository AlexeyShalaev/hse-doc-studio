import { describe, expect, it } from "vitest";

import {
  computeCheckpointReadiness,
  pickActiveProfile,
  type DocumentLike,
  type FormLike,
  type SignaturesStateLike,
  type SubmissionProfile,
} from "./readiness";

type ProfileItem = NonNullable<SubmissionProfile["items"]>[number];

/** Пункт профиля с открытыми гейтами — как их отдаёт бэкенд по умолчанию. */
const item = (
  doc_id: string,
  signatures: string[] = [],
  gates: Partial<Pick<ProfileItem, "skip_if_nda" | "supported_kinds">> = {},
): ProfileItem => ({
  doc_id,
  signatures,
  skip_if_nda: false,
  supported_kinds: ["research", "project"],
  ...gates,
});

/** formIds — базовые id анкет, входящих в пакет точки (её extra_items). */
const profile = (
  items: SubmissionProfile["items"],
  id = "kt1",
  formIds: string[] = [],
): SubmissionProfile => ({
  id,
  name: { ru: "КТ1", en: "CP1" },
  description: { ru: "", en: "" },
  items,
  extra_items: formIds.map((formId) => ({
    source: `.hse-studio/forms/${formId}.json`,
    output_name: `${formId}.md`,
    format: "markdown",
    supported_kinds: ["research", "project"],
  })),
});

const doc = (
  id: string,
  status: DocumentLike["status"],
  errors?: number,
): DocumentLike => ({ id, status, errors });

// Командный экземпляр документа: id = «<def_id>--<slug>», как его отдаёт бэкенд.
const ownedDoc = (
  defId: string,
  owner: string,
  status: DocumentLike["status"],
): DocumentLike => ({
  id: `${defId}--${owner}`,
  def_id: defId,
  owner,
  owner_name: `Автор ${owner}`,
  status,
});

/** Подписано по-настоящему: размещение включено И картинка слота загружена. */
const signed = (docId: string, slotId: string): SignaturesStateLike => ({
  placements: { [docId]: { [slotId]: { enabled: true } } },
  slots: { [slotId]: { png_path: `signatures/${slotId}.png` } },
});

/**
 * Все слоты, встречающиеся в размещениях, снабжаются загруженным PNG.
 * Правило «enabled + png_path» проверяется отдельным тестом; остальные кейсы
 * про резолв слотов, и загруженная картинка для них — фон, а не предмет.
 */
const withUploadedSlots = (
  state: Omit<SignaturesStateLike, "slots">,
): SignaturesStateLike => {
  const slots: Record<string, { png_path: string }> = {};
  for (const bySlot of Object.values(state.placements)) {
    for (const slotId of Object.keys(bySlot)) {
      slots[slotId] = { png_path: `signatures/${slotId}.png` };
    }
  }
  return { ...state, slots };
};

describe("computeCheckpointReadiness", () => {
  it("reports unknown when the profile carries no items", () => {
    expect(
      computeCheckpointReadiness(
        profile(null),
        [doc("thesis", "ok")],
        undefined,
        [],
      ),
    ).toEqual({
      done: 0,
      total: 0,
      isComplete: false,
      isUnknown: true,
      items: [],
      breakdown: {
        documents: { done: 0, total: 0 },
        signatures: { done: 0, total: 0 },
        forms: { done: 0, total: 0 },
      },
      formIds: [],
      blockers: 0,
    });
  });

  it("treats an undefined items list the same as null", () => {
    expect(
      computeCheckpointReadiness(profile(undefined), [], undefined, [])
        .isUnknown,
    ).toBe(true);
  });

  it("skips a document the project does not have", () => {
    const readiness = computeCheckpointReadiness(
      profile([item("thesis"), item("annotation", ["supervisor"])]),
      [doc("thesis", "ok")],
      undefined,
      [],
    );

    // Отсутствующая «Аннотация» не попадает ни в знаменатель, ни в блокеры.
    expect(readiness.total).toBe(1);
    expect(readiness.done).toBe(1);
    expect(readiness.blockers).toBe(0);
    expect(readiness.isComplete).toBe(true);
    expect(readiness.items[1]).toEqual({
      docId: "annotation",
      resolvedDocId: null,
      ownerName: null,
      isApplicable: false,
      isBuilt: false,
      hasWarnings: false,
      hasErrors: false,
      signatures: [],
    });
  });

  // Бэкенд ставит статус в порядке err → warn → ok (trigger_compile): «warn» —
  // это УСПЕШНАЯ сборка, у которой проверки дали предупреждения. Не собран
  // только «draft».
  it("counts a document with check warnings as built", () => {
    const readiness = computeCheckpointReadiness(
      profile([item("thesis")]),
      [doc("thesis", "warn")],
      undefined,
      [],
    );

    expect(readiness.items[0]).toMatchObject({
      isBuilt: true,
      hasWarnings: true,
      hasErrors: false,
    });
    expect(readiness).toMatchObject({ done: 1, total: 1, blockers: 0 });
  });

  it("counts a draft document as not built", () => {
    const readiness = computeCheckpointReadiness(
      profile([item("thesis")]),
      [doc("thesis", "draft")],
      undefined,
      [],
    );

    expect(readiness.items[0]).toMatchObject({
      isBuilt: false,
      hasWarnings: false,
      hasErrors: false,
    });
    expect(readiness).toMatchObject({ done: 0, total: 1, blockers: 1 });
  });

  it("counts a failed document as not built and erroneous", () => {
    const readiness = computeCheckpointReadiness(
      profile([item("thesis")]),
      [doc("thesis", "err")],
      undefined,
      [],
    );

    expect(readiness.items[0]).toMatchObject({
      isBuilt: false,
      hasWarnings: false,
      hasErrors: true,
    });
    expect(readiness).toMatchObject({ done: 0, total: 1, blockers: 1 });
  });

  it("counts a built document with compile errors as not done", () => {
    const readiness = computeCheckpointReadiness(
      profile([item("thesis")]),
      [doc("thesis", "ok", 2)],
      undefined,
      [],
    );

    expect(readiness.items[0]?.hasErrors).toBe(true);
    expect(readiness).toMatchObject({ done: 0, total: 1, blockers: 1 });
  });

  it("adds one unit per signature slot and counts only enabled placements", () => {
    const items = profile([item("thesis", ["supervisor", "student"])]);

    const none = computeCheckpointReadiness(
      items,
      [doc("thesis", "ok")],
      undefined,
      [],
    );
    expect(none).toMatchObject({ done: 1, total: 3, blockers: 2 });

    const one = computeCheckpointReadiness(
      items,
      [doc("thesis", "ok")],
      signed("thesis", "supervisor"),
      [],
    );
    expect(one).toMatchObject({ done: 2, total: 3, blockers: 1 });
    expect(one.items[0]?.signatures).toEqual([
      { slotId: "supervisor", isSigned: true },
      { slotId: "student", isSigned: false },
    ]);
  });

  it("ignores a disabled placement and a placement on another document", () => {
    const readiness = computeCheckpointReadiness(
      profile([item("thesis", ["student"])]),
      [doc("thesis", "ok")],
      withUploadedSlots({
        placements: {
          thesis: { student: { enabled: false } },
          nda: { student: { enabled: true } },
        },
      }),
      [],
    );

    expect(readiness).toMatchObject({ done: 1, total: 2, blockers: 1 });
  });

  it("keeps slot ids verbatim in a solo project", () => {
    // Без выбранного автора суффикс не подставляется вовсе: в одиночном проекте
    // слоты не размножаются, и «student» обязан остаться «student».
    const readiness = computeCheckpointReadiness(
      profile([item("thesis", ["student"])]),
      [doc("thesis", "ok")],
      withUploadedSlots({
        runtime_slots: [{ id: "student" }],
        placements: { thesis: { student: { enabled: true } } },
      }),
      [],
    );

    expect(readiness.items[0]?.signatures).toEqual([
      { slotId: "student", isSigned: true },
    ]);
  });

  it("counts only forms required for the pack, once per project", () => {
    const forms: FormLike[] = [
      { id: "ai_declaration", required_for_pack: true, complete: true },
      { id: "code_link", required_for_pack: true, complete: false },
      { id: "feedback", required_for_pack: false, complete: false },
    ];

    const readiness = computeCheckpointReadiness(
      profile([item("thesis"), item("nda")], "kt1", [
        "ai_declaration",
        "code_link",
        "feedback",
      ]),
      [doc("thesis", "ok"), doc("nda", "ok")],
      undefined,
      forms,
    );

    // 2 документа + 2 обязательные формы; необязательная форма вне счёта.
    expect(readiness).toMatchObject({ done: 3, total: 4, blockers: 1 });
    expect(readiness.isComplete).toBe(false);
    expect(readiness.formIds).toEqual(["ai_declaration", "code_link"]);
    expect(readiness.breakdown).toEqual({
      documents: { done: 2, total: 2 },
      signatures: { done: 0, total: 0 },
      forms: { done: 1, total: 2 },
    });
  });

  // Шапка экрана печатает разбивку рядом с кольцом («7/9 документы · 3/4
  // подписи»). Разойдись сумма с кольцом — на одном экране появятся два ответа
  // на «сколько осталось». Тождество держится тем, что оси накапливаются в тех
  // же циклах; тест сторожит именно его.
  it("keeps the breakdown summing exactly to done and total", () => {
    const forms: FormLike[] = [
      { id: "ai_declaration", required_for_pack: true, complete: true },
      { id: "code_link", required_for_pack: true, complete: false },
    ];
    // Картинка загружена только у автора: подписи руководителя нет, и в
    // «сделано» она не попадёт — нужен разрез с неполной осью.
    const signatures: SignaturesStateLike = {
      placements: {
        thesis: { author: { enabled: true }, supervisor: { enabled: true } },
        nda: { author: { enabled: true } },
      },
      slots: { author: { png_path: "signatures/author.png" } },
    };

    const readiness = computeCheckpointReadiness(
      profile(
        [
          item("thesis", ["author", "supervisor"]),
          item("nda", ["author"]),
          item("missing_doc"),
        ],
        "kt4",
        ["ai_declaration", "code_link"],
      ),
      [doc("thesis", "ok"), doc("nda", "draft")],
      signatures,
      forms,
    );

    const {
      documents,
      signatures: sigs,
      forms: formTally,
    } = readiness.breakdown;

    expect(documents.total + sigs.total + formTally.total).toBe(
      readiness.total,
    );
    expect(documents.done + sigs.done + formTally.done).toBe(readiness.done);
    // Неинстанцированный документ не попадает ни в одну из осей.
    expect(documents.total).toBe(2);
  });

  // Регрессия: экран точки рендерил анкеты собственным фильтром по
  // required_for_pack и показывал «Декларацию ИИ» на КТ1, где её в пакете нет,
  // — рядом с кольцом, которое её справедливо не считало. Список обязан
  // строиться из formIds, поэтому расчёт возвращает их наружу.
  it("reports no forms for a checkpoint whose profile does not carry them", () => {
    const forms: FormLike[] = [
      { id: "ai_declaration", required_for_pack: true, complete: false },
    ];

    const readiness = computeCheckpointReadiness(
      profile([item("thesis")], "kt1", []),
      [doc("thesis", "ok")],
      undefined,
      forms,
    );

    expect(readiness.formIds).toEqual([]);
    expect(readiness).toMatchObject({ done: 1, total: 1, blockers: 0 });
  });

  it("omits a co-author's personal form from the counted ids", () => {
    const forms: FormLike[] = [
      {
        id: "ai_declaration--shalaev",
        required_for_pack: true,
        complete: true,
        owner: "shalaev",
      },
      {
        id: "ai_declaration--ivanov",
        required_for_pack: true,
        complete: false,
        owner: "ivanov",
      },
    ];

    const readiness = computeCheckpointReadiness(
      profile([item("thesis")], "final", ["ai_declaration"]),
      [doc("thesis", "ok")],
      undefined,
      forms,
      "shalaev",
      ["shalaev", "ivanov"],
    );

    expect(readiness.formIds).toEqual(["ai_declaration--shalaev"]);
  });

  it("does not call an empty checkpoint complete", () => {
    const readiness = computeCheckpointReadiness(
      profile([]),
      [],
      undefined,
      [],
    );

    expect(readiness).toMatchObject({
      done: 0,
      total: 0,
      blockers: 0,
      isUnknown: false,
      isComplete: false,
    });
  });
});

describe("computeCheckpointReadiness in a team project", () => {
  // Профиль называет документы по id ОПРЕДЕЛЕНИЯ, а в проекте лежат личные
  // экземпляры обоих авторов плюс общий документ команды.
  const teamProfile = profile([
    item("technical_specification"),
    item("shared_technical_specification"),
  ]);
  const teamDocs: DocumentLike[] = [
    ownedDoc("technical_specification", "shalaev", "ok"),
    ownedDoc("technical_specification", "ivanov", "err"),
    doc("shared_technical_specification", "ok"),
  ];

  it("resolves the selected author's instance and ignores the other one", () => {
    const mine = computeCheckpointReadiness(
      teamProfile,
      teamDocs,
      undefined,
      [],
      "shalaev",
    );

    expect(mine.items[0]).toEqual({
      docId: "technical_specification",
      resolvedDocId: "technical_specification--shalaev",
      ownerName: "Автор shalaev",
      isApplicable: true,
      isBuilt: true,
      hasWarnings: false,
      hasErrors: false,
      signatures: [],
    });
    // Оба документа автора в счёте: сломанное ТЗ соавтора его не касается.
    expect(mine).toMatchObject({ done: 2, total: 2, blockers: 0 });

    const theirs = computeCheckpointReadiness(
      teamProfile,
      teamDocs,
      undefined,
      [],
      "ivanov",
    );

    expect(theirs.items[0]).toMatchObject({
      resolvedDocId: "technical_specification--ivanov",
      ownerName: "Автор ivanov",
      isApplicable: true,
      hasErrors: true,
    });
    expect(theirs).toMatchObject({ done: 1, total: 2, blockers: 1 });
  });

  it("resolves the shared document for every author", () => {
    for (const slug of ["shalaev", "ivanov"]) {
      const readiness = computeCheckpointReadiness(
        teamProfile,
        teamDocs,
        undefined,
        [],
        slug,
      );

      expect(readiness.items[1]).toEqual({
        docId: "shared_technical_specification",
        resolvedDocId: "shared_technical_specification",
        ownerName: null,
        isApplicable: true,
        isBuilt: true,
        hasWarnings: false,
        hasErrors: false,
        signatures: [],
      });
    }
  });

  it("reads signature placements by the real document id", () => {
    const readiness = computeCheckpointReadiness(
      profile([item("technical_specification", ["student"])]),
      teamDocs,
      signed("technical_specification--shalaev", "student"),
      [],
      "shalaev",
    );

    expect(readiness.items[0]?.signatures).toEqual([
      { slotId: "student", isSigned: true },
    ]);
    expect(readiness).toMatchObject({ done: 2, total: 2, blockers: 0 });
  });

  it("ignores a placement stored under the definition id", () => {
    // Ровно тот баг, что и с документами: ключ подписи — id экземпляра, и
    // размещение на id определения не должно засчитываться.
    const readiness = computeCheckpointReadiness(
      profile([item("technical_specification", ["student"])]),
      teamDocs,
      signed("technical_specification", "student"),
      [],
      "shalaev",
    );

    expect(readiness).toMatchObject({ done: 1, total: 2, blockers: 1 });
  });

  // Бэкенд РАЗМНОЖАЕТ личные слоты подписи по авторам: профиль называет слот
  // каталога («author»), а в проекте лежат «author--shalaev» и «author--ivanov»;
  // общие слоты («supervisor») остаются без суффикса.
  const runtimeSlots = [
    { id: "author--shalaev" },
    { id: "author--ivanov" },
    { id: "supervisor" },
  ];
  const slotProfile = profile([
    item("technical_specification", ["author", "supervisor"]),
  ]);

  it("resolves a per-author slot to the selected author's instance", () => {
    const readiness = computeCheckpointReadiness(
      slotProfile,
      teamDocs,
      withUploadedSlots({
        runtime_slots: runtimeSlots,
        placements: {
          "technical_specification--shalaev": {
            "author--shalaev": { enabled: true },
            supervisor: { enabled: true },
          },
        },
      }),
      [],
      "shalaev",
    );

    expect(readiness.items[0]?.signatures).toEqual([
      { slotId: "author--shalaev", isSigned: true },
      // Общий слот суффикса не имеет и обязан находиться как раньше.
      { slotId: "supervisor", isSigned: true },
    ]);
    expect(readiness).toMatchObject({ done: 3, total: 3, blockers: 0 });
  });

  it("never consults the co-author's slot", () => {
    const readiness = computeCheckpointReadiness(
      slotProfile,
      teamDocs,
      withUploadedSlots({
        runtime_slots: runtimeSlots,
        placements: {
          // Подписал только соавтор — для выбранного автора это «не подписано».
          "technical_specification--shalaev": {
            "author--ivanov": { enabled: true },
            supervisor: { enabled: false },
          },
        },
      }),
      [],
      "shalaev",
    );

    expect(readiness.items[0]?.signatures).toEqual([
      { slotId: "author--shalaev", isSigned: false },
      { slotId: "supervisor", isSigned: false },
    ]);
    expect(readiness).toMatchObject({ done: 1, total: 3, blockers: 2 });
  });

  it("keeps the catalog slot id when the author has no personal instance", () => {
    // Слот есть, но он общий: суффикса в runtime_slots нет — читаем как есть.
    const readiness = computeCheckpointReadiness(
      profile([item("shared_technical_specification", ["supervisor"])]),
      teamDocs,
      withUploadedSlots({
        runtime_slots: runtimeSlots,
        placements: {
          shared_technical_specification: { supervisor: { enabled: true } },
        },
      }),
      [],
      "ivanov",
    );

    expect(readiness.items[0]?.signatures).toEqual([
      { slotId: "supervisor", isSigned: true },
    ]);
  });

  // ОБЩИЙ документ команды подписывают ВСЕ авторы: бэкенд размножает личный
  // слот по каждому («author--shalaev», «author--ivanov») в размещениях именно
  // этого документа. Считать одного выбранного значило бы показать «всё
  // готово» там, где упаковка упадёт на подписи соавтора.
  const teamSlugs = ["shalaev", "ivanov"];
  const sharedRuntimeSlots = [
    { id: "author--shalaev" },
    { id: "author--ivanov" },
    { id: "supervisor" },
    { id: "co_supervisor" },
  ];
  const sharedProfile = profile([
    item("shared_technical_specification", ["author", "supervisor"]),
  ]);

  it("requires the shared document from every author, each signed on its own", () => {
    const readiness = computeCheckpointReadiness(
      sharedProfile,
      teamDocs,
      withUploadedSlots({
        runtime_slots: sharedRuntimeSlots,
        placements: {
          shared_technical_specification: {
            "author--shalaev": { enabled: true },
            "author--ivanov": { enabled: false },
            supervisor: { enabled: false },
          },
        },
      }),
      [],
      "shalaev",
      teamSlugs,
    );

    expect(readiness.items[0]?.signatures).toEqual([
      { slotId: "author--shalaev", isSigned: true },
      // Подпись соавтора — отдельная единица счёта, а не следствие первой.
      { slotId: "author--ivanov", isSigned: false },
      { slotId: "supervisor", isSigned: false },
    ]);
    // Документ + три подписи; закрыта одна.
    expect(readiness).toMatchObject({ done: 2, total: 4, blockers: 2 });
  });

  it("closes the shared document only when every author has signed", () => {
    const allSigned = computeCheckpointReadiness(
      sharedProfile,
      teamDocs,
      withUploadedSlots({
        runtime_slots: sharedRuntimeSlots,
        placements: {
          shared_technical_specification: {
            "author--shalaev": { enabled: true },
            "author--ivanov": { enabled: true },
            supervisor: { enabled: true },
          },
        },
      }),
      [],
      "shalaev",
      teamSlugs,
    );

    expect(allSigned).toMatchObject({ done: 4, total: 4, blockers: 0 });
    expect(allSigned.isComplete).toBe(true);
  });

  it("keeps a slot without per-author instances a single unit", () => {
    const readiness = computeCheckpointReadiness(
      profile([
        item("shared_technical_specification", ["supervisor", "co_supervisor"]),
      ]),
      teamDocs,
      withUploadedSlots({
        runtime_slots: sharedRuntimeSlots,
        placements: {
          shared_technical_specification: { supervisor: { enabled: true } },
        },
      }),
      [],
      "shalaev",
      teamSlugs,
    );

    // Руководителей не размножают по авторам: у обоих слотов суффикса нет.
    expect(readiness.items[0]?.signatures).toEqual([
      { slotId: "supervisor", isSigned: true },
      { slotId: "co_supervisor", isSigned: false },
    ]);
  });

  it("keeps a personal document at one unit even with the whole team known", () => {
    const readiness = computeCheckpointReadiness(
      profile([item("technical_specification", ["author"])]),
      teamDocs,
      withUploadedSlots({
        runtime_slots: sharedRuntimeSlots,
        placements: {
          "technical_specification--shalaev": {
            "author--shalaev": { enabled: false },
            // Личное ТЗ автора соавтор не подписывает — этой подписи здесь
            // взяться неоткуда, и в счёт она попасть не должна.
            "author--ivanov": { enabled: true },
          },
        },
      }),
      [],
      "shalaev",
      teamSlugs,
    );

    expect(readiness.items[0]?.signatures).toEqual([
      { slotId: "author--shalaev", isSigned: false },
    ]);
    expect(readiness).toMatchObject({ done: 1, total: 2, blockers: 1 });
  });

  it("falls back to the bare slot id when no author instance exists at all", () => {
    // Проект старше размножения слотов: личных экземпляров нет ни у кого, и
    // единственная честная единица счёта — каталожный слот.
    const readiness = computeCheckpointReadiness(
      sharedProfile,
      teamDocs,
      withUploadedSlots({
        placements: {
          shared_technical_specification: {
            author: { enabled: true },
            supervisor: { enabled: true },
          },
        },
      }),
      [],
      "shalaev",
      teamSlugs,
    );

    expect(readiness.items[0]?.signatures).toEqual([
      { slotId: "author", isSigned: true },
      { slotId: "supervisor", isSigned: true },
    ]);
  });

  it("counts the author's own and the shared form, never a co-author's", () => {
    const forms: FormLike[] = [
      {
        id: "ai_declaration--shalaev",
        owner: "shalaev",
        required_for_pack: true,
        complete: false,
      },
      {
        id: "ai_declaration--ivanov",
        owner: "ivanov",
        required_for_pack: true,
        complete: true,
      },
      { id: "consent", owner: null, required_for_pack: true, complete: true },
      {
        id: "code_link--shalaev",
        owner: "shalaev",
        required_for_pack: false,
        complete: false,
      },
    ];

    const readiness = computeCheckpointReadiness(
      profile([item("shared_technical_specification")], "kt1", [
        "ai_declaration",
        "consent",
        "code_link",
      ]),
      teamDocs,
      undefined,
      forms,
      "shalaev",
    );

    // 1 документ + своя (пустая) декларация + общая анкета; анкета соавтора и
    // необязательная форма вне счёта.
    expect(readiness).toMatchObject({ done: 2, total: 3, blockers: 1 });
  });

  it("keeps a document no author owns non-applicable", () => {
    const readiness = computeCheckpointReadiness(
      profile([
        item("technical_specification"),
        item("annotation", ["supervisor"]),
      ]),
      teamDocs,
      undefined,
      [],
      "shalaev",
    );

    expect(readiness.items[1]).toMatchObject({
      docId: "annotation",
      resolvedDocId: null,
      isApplicable: false,
    });
    expect(readiness).toMatchObject({ done: 1, total: 1, blockers: 0 });
  });

  it("leaves a solo project untouched when no author is selected", () => {
    // Регрессионный сторож: в одиночном проекте def_id == id, владельцев нет,
    // и результат обязан совпадать с расчётом без пятого аргумента.
    const soloProfile = profile(
      [item("thesis", ["student"]), item("annotation")],
      "kt1",
      ["ai_declaration", "code_link"],
    );
    const soloDocs = [doc("thesis", "ok"), doc("annotation", "draft")];
    const soloForms: FormLike[] = [
      { id: "ai_declaration", required_for_pack: true, complete: true },
      { id: "code_link", required_for_pack: false, complete: false },
    ];
    const placements = signed("thesis", "student");

    const legacy = computeCheckpointReadiness(
      soloProfile,
      soloDocs,
      placements,
      soloForms,
    );

    expect(legacy).toMatchObject({ done: 3, total: 4, blockers: 1 });
    expect(
      computeCheckpointReadiness(
        soloProfile,
        soloDocs,
        placements,
        soloForms,
        null,
      ),
    ).toEqual(legacy);
    expect(
      computeCheckpointReadiness(
        soloProfile,
        soloDocs,
        placements,
        soloForms,
        undefined,
      ),
    ).toEqual(legacy);
    // Список авторов без выбранного автора не значит ничего: одиночный проект
    // размножения слотов не знает, и «student» обязан остаться «student».
    expect(
      computeCheckpointReadiness(
        soloProfile,
        soloDocs,
        placements,
        soloForms,
        null,
        ["shalaev", "ivanov"],
      ),
    ).toEqual(legacy);
  });
});

describe("pickActiveProfile", () => {
  const kt1 = profile([], "kt1");
  const kt2 = profile([], "kt2");
  const kt3 = profile([], "kt3");

  it("returns null for an empty list", () => {
    expect(pickActiveProfile([], [], null)).toBeNull();
  });

  it("prefers the pinned profile", () => {
    expect(pickActiveProfile([kt1, kt2, kt3], [], "kt3")).toBe(kt3);
  });

  it("falls back to the nearest unpacked profile when the pin is stale", () => {
    expect(pickActiveProfile([kt1, kt2, kt3], ["kt1"], "gone")).toBe(kt2);
  });

  it("returns the last profile when everything is already packed", () => {
    expect(
      pickActiveProfile([kt1, kt2, kt3], ["kt1", "kt2", "kt3"], null),
    ).toBe(kt3);
  });

  it("drops an item whose supported_kinds excludes the project kind", () => {
    // thesis существует и в исследовательской работе, но на КТ2 её сдают
    // «Отчётом ВКР» — пункт гейтится видом, хотя документ в проекте есть.
    const items = [
      item("interim_report"),
      item("thesis", [], { supported_kinds: ["project"] }),
    ];
    const docs = [doc("interim_report", "ok"), doc("thesis", "draft")];

    const research = computeCheckpointReadiness(
      profile(items),
      docs,
      undefined,
      [],
      null,
      [],
      { kind: "research" },
    );
    expect(research).toMatchObject({ done: 1, total: 1, blockers: 0 });

    const project = computeCheckpointReadiness(
      profile(items),
      docs,
      undefined,
      [],
      null,
      [],
      { kind: "project" },
    );
    expect(project).toMatchObject({ done: 1, total: 2, blockers: 1 });
  });

  it("drops a skip_if_nda item only when the project is under NDA", () => {
    const items = [
      item("thesis"),
      item("source_listing", [], { skip_if_nda: true }),
    ];
    const docs = [doc("thesis", "ok"), doc("source_listing", "draft")];

    expect(
      computeCheckpointReadiness(
        profile(items),
        docs,
        undefined,
        [],
        null,
        [],
        {
          isNda: true,
        },
      ),
    ).toMatchObject({ done: 1, total: 1, blockers: 0 });

    expect(
      computeCheckpointReadiness(
        profile(items),
        docs,
        undefined,
        [],
        null,
        [],
        {
          isNda: false,
        },
      ),
    ).toMatchObject({ done: 1, total: 2, blockers: 1 });
  });

  it("applies no gate when the scope is omitted", () => {
    // Обратная совместимость вызова без области: гейты не сужают состав.
    const items = [item("thesis", [], { supported_kinds: ["project"] })];
    expect(
      computeCheckpointReadiness(
        profile(items),
        [doc("thesis", "ok")],
        undefined,
        [],
      ),
    ).toMatchObject({ done: 1, total: 1 });
  });

  it("ignores a required form that this checkpoint does not package", () => {
    // Реальный случай: «Декларация ИИ» обязательна к сдаче вообще
    // (required_for_pack), но входит только в пакет КТ4. На КТ1 её быть в счёте
    // не должно — иначе точка показывает блокер, который к ней не относится.
    const forms: FormLike[] = [
      { id: "ai_declaration", required_for_pack: true, complete: false },
    ];
    const docs = [doc("topic_presentation", "ok")];

    const kt1 = computeCheckpointReadiness(
      profile([item("topic_presentation")], "checkpoint-1", []),
      docs,
      undefined,
      forms,
    );
    expect(kt1).toMatchObject({ done: 1, total: 1, blockers: 0 });
    expect(kt1.isComplete).toBe(true);

    const kt4 = computeCheckpointReadiness(
      profile([item("topic_presentation")], "final", ["ai_declaration"]),
      docs,
      undefined,
      forms,
    );
    expect(kt4).toMatchObject({ done: 1, total: 2, blockers: 1 });
  });

  it("does not count an enabled placement whose slot has no uploaded PNG", () => {
    // Студент включает размещение, чтобы посмотреть, куда ляжет штамп, но PNG
    // не загружает. Бэкенд при упаковке требует и enabled, и png_path
    // (_validated_signatures), поэтому кольцо не имеет права зеленеть.
    const placedButNoPng = {
      placements: { thesis: { student: { enabled: true } } },
      slots: { student: { png_path: null } },
    };

    const readiness = computeCheckpointReadiness(
      profile([item("thesis", ["student"])]),
      [doc("thesis", "ok")],
      placedButNoPng,
      [],
    );
    expect(readiness).toMatchObject({ done: 1, total: 2, blockers: 1 });
    expect(readiness.items[0]?.signatures).toEqual([
      { slotId: "student", isSigned: false },
    ]);

    // Та же расстановка, но картинка загружена — единица закрывается.
    const uploaded = computeCheckpointReadiness(
      profile([item("thesis", ["student"])]),
      [doc("thesis", "ok")],
      signed("thesis", "student"),
      [],
    );
    expect(uploaded).toMatchObject({ done: 2, total: 2, blockers: 0 });
  });
});
