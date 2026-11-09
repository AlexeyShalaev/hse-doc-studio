import type {
  RouteSignMethod,
  SigningFailure,
  SigningKeyRequest,
  SigningTask,
} from "@entities/signing-route";

/**
 * Что блоку подписи даёт страница подписанта (`SigningSlotContext` страницы, тот же вид):
 * задача, занятость и действия с отпечатками последнего показа.
 */
export type SigningInlineContext = {
  projectId: string;
  routeId: string;
  task: SigningTask;
  busy: boolean;
  /** Код отказа последнего действия страницы: окно пароля показывает его у себя. */
  failure: string | null;
  expected: Record<string, string>;
  approve: (options?: {
    method?: RouteSignMethod | null;
    sign?: SigningKeyRequest | null;
    expected?: Record<string, string>;
  }) => Promise<SigningTask | null>;
  sign: (
    key: SigningKeyRequest,
    expected?: Record<string, string>,
  ) => Promise<SigningTask | null>;
};

/** Чем ставится ЭП: ключом Студии на сервере, плагином КриптоПро или готовым файлом подписи. */
export type SignWay = "studio" | "cryptopro" | "file";

/** Чего не хватает главной кнопке. */
export type InlineBlocker = "image" | "plate" | "way" | "key" | "files";

/** Что раскрыто внутри блока. */
export type InlinePanel = "draw" | "editor" | "key-create" | "key-import";

/** Окно поверх страницы. */
export type InlinePrompt = "passphrase" | "cryptopro-sign" | "cryptopro-plate";

/** Выбор подписанта и состояние блока: одно на блок «Как подписать» и главную кнопку. */
export type InlineUiState = {
  /** Способ, выбранный на странице; null: способ слота. */
  method: RouteSignMethod | null;
  way: SignWay | null;
  /** Ключ Студии, выбранный или созданный здесь; null: ключ по умолчанию. */
  identityId: string | null;
  /** Ключ Студии, данные которого блок уже положил на плашку. */
  plateKeyId: string | null;
  /** «Запомнить для других проектов». */
  remember: boolean;
  /** Готовые подписи по слотам: ключ `документ/слот`. */
  files: Record<string, File>;
  panel: InlinePanel | null;
  /** Раскрыт выбор другого ключа или сертификата. */
  moreOpen: boolean;
  prompt: InlinePrompt | null;
  busy: boolean;
  failure: SigningFailure | null;
  /** Чего не хватило при нажатии главной кнопки: блок подсвечивает это место. */
  nudge: InlineBlocker | null;
};

export type InlineUi = {
  state: InlineUiState;
  patch: (patch: Partial<InlineUiState>) => void;
};

export const INITIAL_INLINE_UI: InlineUiState = {
  method: null,
  way: null,
  identityId: null,
  plateKeyId: null,
  remember: false,
  files: {},
  panel: null,
  moreOpen: false,
  prompt: null,
  busy: false,
  failure: null,
  nudge: null,
};
