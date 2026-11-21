import type { QueryClient } from "@tanstack/react-query";
import {
  packOutcomeKeys,
  packStudioKeys,
  type OutcomeElementRef,
  type PackOutcomeRequest,
  type PackVersionRef,
} from "@entities/pack-studio";
import {
  VKR_INPUTS,
  VKR_OUTCOME,
  explainFor,
  referenceModel,
} from "@entities/pack-studio/reference";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import {
  GALLERY_REF,
  GALLERY_WORKSPACE,
  SpaceGalleryFrame,
} from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import { defineSpaceSlots } from "../shell/spaceSlots";
import { DetailsPanel } from "./DetailsPanel";
import { feedKey, writeEditFeed } from "./edit/editFeed";
import {
  pushEdit,
  emptyHistory,
} from "@features/pack-outcome/lib/edit/history";
import type { RuleEdit } from "@features/pack-outcome/lib/edit/plan";

// Галерея «Подробностей» (S7): правая колонка «Результата» на эталонах контракта, без сервера.
// Результат, вопрос «почему так» и описание версии кладутся в кэш запросов; центр экрана это
// пустая заглушка, ради колонки справа. Каждое состояние живёт на своей версии, потому что
// лента правок хранится вне React и по версии.

const WS = GALLERY_WORKSPACE.id;
const REQUEST: PackOutcomeRequest = { state: "work_tree" };

const refOf = (version: string): PackVersionRef => ({
  ...GALLERY_REF,
  version,
});

const element = (selection: string): OutcomeElementRef => {
  const cut = selection.indexOf(":");
  return {
    section: selection.slice(0, cut) as OutcomeElementRef["section"],
    id: selection.slice(cut + 1),
  };
};

/** Результат, условия и «почему так» выбранного элемента: как их отдаёт сервер. */
const seedDetails = (
  client: QueryClient,
  version: string,
  selection: string | null,
  options: { model?: boolean } = {},
) => {
  const ref = refOf(version);
  const outcome = { ...VKR_OUTCOME, workspace_id: WS, ...ref };
  client.setQueryData(packOutcomeKeys.result(WS, ref, REQUEST), outcome);
  client.setQueryData(packOutcomeKeys.inputs(WS, ref, "work_tree"), {
    ...VKR_INPUTS,
    workspace_id: WS,
    ...ref,
  });
  if (selection) {
    const target = element(selection);
    const data = explainFor(outcome, target, "vkr");
    if (data) {
      client.setQueryData(
        packOutcomeKeys.explain(WS, ref, { ...REQUEST, element: target }),
        { data, etag: null },
      );
    }
  }
  if (options.model) {
    client.setQueryData(
      packStudioKeys.model(WS, ref),
      referenceModel(WS, "hse-cs-se", "vkr", ref.version),
    );
  }
};

const Center = () => (
  <div style={{ color: "var(--fg-2)", fontSize: "0.8125rem" }}>
    Центр «Результата»: части результата
  </div>
);

const screenSlots = defineSpaceSlots({
  main: { result: Center },
  details: { result: () => <DetailsPanel /> },
});
const editingSlots = defineSpaceSlots({
  main: { result: Center },
  details: { result: () => <DetailsPanel initialEditing /> },
});

const DOC = "documents:technical_specification";
const NOT_IN = "documents:operator_manual";
const FIELD = "forms:ai_declaration/tools";
const STEP = "route:pdp-application/step/2";

const FAKE_EDIT = (id: string): RuleEdit => ({
  id,
  file: "files/technical_specification/doc.yaml",
  pointer: "/supported_kinds",
  action: "set",
  subject: "supported_kinds",
  place: "technical_specification",
  forward: [],
  inverse: [],
  before: {
    kind: "record",
    pointer: "/supported_kinds",
    exists: true,
    value: [],
  },
  after: {
    kind: "record",
    pointer: "/supported_kinds",
    exists: true,
    value: [],
  },
  at: Date.parse("2026-11-21T10:15:00Z"),
});

/** Правка внесена, результат пересчитан: плашка «что изменилось» и лента правок. */
const seedFeed = (version: string) => {
  const history = pushEdit(emptyHistory, FAKE_EDIT("gallery-edit-1"));
  writeEditFeed(feedKey(WS, refOf(version)), {
    history,
    delta: {
      direction: "apply",
      edit: FAKE_EDIT("gallery-edit-1"),
      items: [
        {
          symbol: "-",
          section: "documents",
          id: "technical_specification",
          label: "Техническое задание",
          before: null,
          after: null,
        },
        {
          symbol: "~",
          section: "points",
          id: "checkpoint-1",
          label: "Точка 1: что сдавать",
          before: null,
          after: null,
        },
      ],
    },
  });
};

type Spec = {
  id: string;
  title: string;
  note: string;
  version: string;
  selection: string | null;
  phone?: boolean;
  editing?: boolean;
  model?: boolean;
  feed?: boolean;
};

const entry = (spec: Spec): GalleryEntry => {
  const search = [
    spec.selection ? `sel=${encodeURIComponent(spec.selection)}` : "",
  ]
    .filter(Boolean)
    .join("&");
  return {
    id: spec.id,
    title: spec.title,
    note: spec.note,
    frame: spec.phone ? "plain" : "screen",
    width: spec.phone ? 390 : 1280,
    seed: (client) => {
      seedDetails(client, spec.version, spec.selection, {
        model: spec.model === true,
      });
      if (spec.feed) seedFeed(spec.version);
    },
    render: () => (
      <SpaceGalleryFrame
        height={spec.phone ? "40rem" : "36rem"}
        search={search}
        version={spec.version}
      >
        <SpaceScreen
          slots={spec.editing ? editingSlots : screenSlots}
          phone={spec.phone === true}
        />
      </SpaceGalleryFrame>
    ),
  };
};

export const galleryEntries: GalleryEntry[] = [
  entry({
    id: "sp_details_none",
    title: "Подробности: ничего не выбрано",
    note: "Заголовок «Что здесь можно сделать» и подсказка вместо пустого «Элемент не выбран».",
    version: "2026.1.3",
    selection: null,
  }),
  entry({
    id: "sp_details_document",
    title: "Подробности: документ входит в комплект",
    note: "«Почему так» предложениями, «Что изменится, если…», «Изменить условия».",
    version: "2026.1.3",
    selection: DOC,
  }),
  entry({
    id: "sp_details_not_in",
    title: "Подробности: документ не вошёл в комплект",
    note: "Причина простыми словами и пометка про правило, встроенное в Студию.",
    version: "2026.1.3",
    selection: NOT_IN,
  }),
  entry({
    id: "sp_details_field",
    title: "Подробности: поле анкеты скрыто",
    note: "Условие показа поля: что сейчас и при каком ответе оно появится.",
    version: "2026.1.3",
    selection: FIELD,
  }),
  entry({
    id: "sp_details_route",
    title: "Подробности: шаг подписания",
    note: "Шаг маршрута без внутренних слов: решения про подписи пересказаны предложениями.",
    version: "2026.1.3",
    selection: STEP,
  }),
  entry({
    id: "sp_details_edit",
    title: "Подробности: правка условия",
    note: "Мини-форма по месту: фраза и чипы. Каждое изменение сразу пишется в черновик.",
    version: "2026.1.3",
    selection: DOC,
    editing: true,
    model: true,
  }),
  entry({
    id: "sp_details_delta",
    title: "Подробности: после правки",
    note: "Плашка «Результат изменился» и лента правок с «Отменить» и «Повторить».",
    version: "2026.1.4",
    selection: DOC,
    feed: true,
    model: true,
  }),
  entry({
    id: "sp_details_released",
    title: "Подробности: выпущенная версия",
    note: "Вместо «Изменить условия» кнопка «Править копию»: номер подберётся сам.",
    version: "2026.1.2",
    selection: DOC,
  }),
  entry({
    id: "sp_details_phone",
    title: "Подробности: шторка на телефоне",
    note: "Снизу, до 60% высоты, с ручкой. Те же кнопки, правка условия доступна.",
    version: "2026.1.3",
    selection: DOC,
    phone: true,
  }),
  entry({
    id: "sp_details_phone_edit",
    title: "Подробности: правка на телефоне",
    note: "Форма во всю ширину шторки, чипы с зоной касания не меньше 40 px.",
    version: "2026.1.5",
    selection: DOC,
    phone: true,
    editing: true,
    model: true,
  }),
];
