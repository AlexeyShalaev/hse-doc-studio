import type {
  RouteSignMethod,
  SigningKeyInfo,
  SigningTask,
  SigningTaskAction,
  SigningTaskMe,
} from "@entities/signing-route";
import type { InlineBlocker, InlineUiState, SignWay } from "./types";

// Чистые правила блока подписи на странице подписанта (docs/design/signing-route.md, 3.2,
// 4.2, 4.4): что показать и что сделает главная кнопка по задаче сервера и выбору человека.

export type KeyOption = {
  id: string;
  label: string;
  kind: string;
  protected: boolean;
};

/** Свой слот, который ещё ждёт подписи. */
export type PendingSlot = {
  /** `документ/слот`: ключ готовой подписи в состоянии блока. */
  key: string;
  docId: string;
  slotId: string;
  docName: Record<string, string>;
  frozen: boolean;
  pdfUrl: string;
};

export type InlinePlan = {
  action: SigningTaskAction;
  /** Способ с учётом выбора на странице. */
  method: RouteSignMethod;
  /** Из чего выбирать; пусто, если выбора нет. */
  methods: RouteSignMethod[];
  /** Что передать в `approve.method`; null: способ слота не меняется. */
  methodChange: RouteSignMethod | null;
  block: "image" | "esign";
  /** Документы со своими слотами уже зафиксированы: видимый слой менять нельзя. */
  frozen: boolean;
  /** Данные плашки ещё можно задать или сменить. */
  canSetPlate: boolean;
  /** Этим нажатием ставится и сама ЭП. */
  needsSign: boolean;
  serverKeys: boolean;
  ways: SignWay[];
  way: SignWay | null;
  keys: KeyOption[];
  key: KeyOption | null;
  slots: PendingSlot[];
  label: "approve" | "approve_and_sign" | "sign";
  blocker: InlineBlocker | null;
  /** Готовая подпись до фиксации: сейчас только согласие, подпись следующим шагом. */
  signAfterFreeze: boolean;
};

export const isCryptoMethod = (method: RouteSignMethod | null): boolean =>
  method === "detached" || method === "pades";

/** Способ: выбранный на странице, если он разрешён; иначе способ слота; иначе первый разрешённый. */
export const chosenMethod = (
  me: SigningTaskMe,
  picked: RouteSignMethod | null,
): RouteSignMethod | null => {
  if (picked !== null && me.methods.includes(picked)) return picked;
  if (
    me.method !== null &&
    (me.methods.length === 0 || me.methods.includes(me.method))
  )
    return me.method;
  return me.methods[0] ?? me.method;
};

export const slotKey = (docId: string, slotId: string): string =>
  `${docId}/${slotId}`;

export const pendingSlots = (task: SigningTask): PendingSlot[] =>
  task.docs.flatMap((doc) =>
    doc.mine
      .filter((slot) => slot.status !== "signed")
      .map((slot) => ({
        key: slotKey(doc.doc_id, slot.slot_id),
        docId: doc.doc_id,
        slotId: slot.slot_id,
        docName: doc.name,
        frozen: doc.frozen,
        pdfUrl: doc.pdf_url,
      })),
  );

/** Ключи Студии: ключ по умолчанию первым. Без списка (ещё грузится) только он. */
export const keyOptions = (
  defaultKey: SigningKeyInfo | null,
  identities: readonly KeyOption[] | undefined,
): KeyOption[] => {
  const first: KeyOption[] = defaultKey
    ? [
        {
          id: defaultKey.id,
          label: defaultKey.label,
          kind: defaultKey.kind,
          protected: defaultKey.protected,
        },
      ]
    : [];
  const rest = (identities ?? []).filter((key) => key.id !== defaultKey?.id);
  // Список точнее сводки задачи (защита паролем): берём запись из него, если она есть.
  const known = identities?.find((key) => key.id === defaultKey?.id);
  return [...(known ? [known] : first), ...rest];
};

const waysOf = (method: RouteSignMethod, serverKeys: boolean): SignWay[] => {
  const studio: SignWay[] = serverKeys ? ["studio"] : [];
  // ЭП внутри PDF ставит только сервер своим ключом; открепленную можно принести готовой.
  return method === "pades" ? studio : [...studio, "cryptopro", "file"];
};

type Choice = Pick<InlineUiState, "method" | "way" | "identityId" | "files">;

/** null: подпись в документе не нужна (согласующий без слотов), блок страницы не меняется. */
export const inlinePlan = (
  task: SigningTask,
  choice: Choice,
  identities: readonly KeyOption[] | undefined,
): InlinePlan | null => {
  const { me } = task;
  const action = me.next_action;
  if (
    action !== "approve" &&
    action !== "approve_and_sign" &&
    action !== "sign"
  )
    return null;
  // Способ меняется только вместе с согласием.
  const method = chosenMethod(me, action === "sign" ? null : choice.method);
  if (method === null) return null;

  const slots = pendingSlots(task);
  const frozen = slots.length > 0 && slots.every((slot) => slot.frozen);
  const crypto = isCryptoMethod(method);
  const needsSign = crypto && action !== "approve";
  const serverKeys = me.keys.server_keys_allowed;
  const ways = crypto ? waysOf(method, serverKeys) : [];
  const way =
    choice.way !== null && ways.includes(choice.way)
      ? choice.way
      : ways.includes("studio")
        ? "studio"
        : null;
  const keys = serverKeys ? keyOptions(me.keys.default_key, identities) : [];
  const key =
    keys.find((item) => item.id === choice.identityId) ?? keys[0] ?? null;
  const canSetPlate = action !== "sign" && !frozen;
  const base = {
    action,
    method,
    methods: action !== "sign" && me.methods.length > 1 ? me.methods : [],
    methodChange: method === me.method ? null : method,
    frozen,
    canSetPlate,
    needsSign,
    serverKeys,
    ways,
    way,
    keys,
    key,
    slots,
  };

  if (!crypto)
    return {
      ...base,
      block: "image",
      label: "approve",
      blocker: me.image_ready ? null : "image",
      signAfterFreeze: false,
    };
  if (!needsSign)
    return {
      ...base,
      block: "esign",
      label: "approve",
      blocker: me.plate === null ? "plate" : null,
      signAfterFreeze: false,
    };

  // Готовую подпись делают над итоговым PDF: до фиксации его ещё нет.
  const signAfterFreeze = way === "file" && !frozen;
  const blocker = ((): InlineBlocker | null => {
    if (way === null) return "way";
    if (way === "studio") return key === null ? "key" : null;
    if (way === "cryptopro") return null;
    // Ключ Студии и сертификат КриптоПро заполняют плашку сами, готовой подписи нужен файл.
    if (me.plate === null && canSetPlate) return "plate";
    if (signAfterFreeze) return null;
    return slots.every((slot) => choice.files[slot.key] !== undefined)
      ? null
      : "files";
  })();
  return {
    ...base,
    block: "esign",
    label:
      action === "sign"
        ? "sign"
        : signAfterFreeze
          ? "approve"
          : "approve_and_sign",
    blocker,
    signAfterFreeze,
  };
};

/** Подпись главной кнопки по ситуации (раздел 4.4): ключи словаря `signing`. */
export const PRIMARY_LABEL_KEY = {
  approve: "actions.approve",
  approve_and_sign: "actions.approveAndSign",
  sign: "actions.sign",
} as const satisfies Record<InlinePlan["label"], string>;
