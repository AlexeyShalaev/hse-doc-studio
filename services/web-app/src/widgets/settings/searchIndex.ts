// Content-level search index for the Settings page.
//
// The sidebar search matches against this index (setting label + keywords), not
// just the section menu names — so typing "движок", "ollama" or "сертификат"
// surfaces the individual setting and jumps straight to it.
//
// `labelKey` is an i18n key into the `settings:search.*` namespace (the displayed
// label follows the interface language). `keywords` stay BILINGUAL on purpose so
// search matches whether the user types in Russian or English regardless of UI
// language.
//
// Each entry's `anchorId` MUST match an `anchorId`/`id` rendered by the section
// component (via <Setting anchorId> / <SettingHead anchorId> or a plain id on a
// sub-block). Keep this list in sync when settings are added or relabelled.

export type SettingsSectionId =
  | "appearance"
  | "account"
  | "organizations"
  | "profile"
  | "compiler"
  | "fonts"
  | "checks"
  | "presentations"
  | "providers"
  | "local-models"
  | "agent-personas"
  | "signing"
  | "disk"
  | "data"
  | "git-access"
  | "runners"
  | "about";

export type SettingSearchEntry = {
  sectionId: SettingsSectionId;
  anchorId: string;
  // i18n key (relative to the `settings` namespace), e.g. "search.appearanceTheme".
  labelKey: string;
  keywords?: readonly string[];
};

export const SETTINGS_SEARCH_INDEX: readonly SettingSearchEntry[] = [
  // ── Внешний вид ──────────────────────────────────────────────
  {
    sectionId: "appearance",
    anchorId: "appearance",
    labelKey: "search.appearance",
    keywords: ["оформление", "appearance", "интерфейс", "ui"],
  },
  {
    sectionId: "appearance",
    anchorId: "appearance-theme",
    labelKey: "search.appearanceTheme",
    keywords: [
      "dark",
      "light",
      "blueprint",
      "system",
      "auto",
      "системная",
      "системная тема",
      "авто",
      "тёмная",
      "темная",
      "светлая",
      "navy",
      "paper",
      "цвет",
      "оформление",
      "theme",
    ],
  },
  {
    sectionId: "appearance",
    anchorId: "appearance-density",
    labelKey: "search.appearanceDensity",
    keywords: [
      "свободная",
      "плотная",
      "compact",
      "comfortable",
      "density",
      "отступы",
    ],
  },
  {
    sectionId: "appearance",
    anchorId: "appearance-language",
    labelKey: "search.appearanceLanguage",
    keywords: [
      "русский",
      "english",
      "ru",
      "en",
      "language",
      "локализация",
      "перевод",
    ],
  },

  // ── Организации (серверный режим) ────────────────────────────
  {
    sectionId: "organizations",
    anchorId: "organizations",
    labelKey: "search.organizations",
    keywords: [
      "организации",
      "организация",
      "группы",
      "выйти из организации",
      "роль",
      "organizations",
      "groups",
      "leave",
      "role",
    ],
  },

  // ── Аккаунт (серверный режим) ────────────────────────────────
  {
    sectionId: "account",
    anchorId: "account",
    labelKey: "search.account",
    keywords: ["аккаунт", "учётная запись", "профиль", "account", "profile"],
  },
  {
    sectionId: "account",
    anchorId: "account-email",
    labelKey: "search.accountEmail",
    keywords: ["почта", "e-mail", "email", "mail", "адрес", "сменить почту"],
  },
  {
    sectionId: "account",
    anchorId: "account-password",
    labelKey: "search.accountPassword",
    keywords: ["пароль", "password", "сменить пароль", "смена пароля"],
  },
  {
    sectionId: "account",
    anchorId: "account-commit",
    labelKey: "search.accountCommit",
    keywords: [
      "подпись",
      "коммиты",
      "версии",
      "noreply",
      "commit",
      "author",
      "signature",
      "приватность",
      "privacy",
    ],
  },
  {
    sectionId: "account",
    anchorId: "account-sessions",
    labelKey: "search.accountSessions",
    keywords: [
      "сессии",
      "устройства",
      "выйти",
      "sessions",
      "devices",
      "sign out",
    ],
  },

  // ── Автор версий ─────────────────────────────────────────────
  {
    sectionId: "profile",
    anchorId: "profile",
    labelKey: "search.profile",
    keywords: [
      "автор",
      "автор версий",
      "автор коммитов",
      "подпись",
      "профиль",
      "author",
      "commit",
      "profile",
      "signature",
      "git",
      "версии",
    ],
  },
  {
    sectionId: "profile",
    anchorId: "profile-name",
    labelKey: "search.profileName",
    keywords: ["имя", "фио", "name", "author", "автор", "коммиты"],
  },
  {
    sectionId: "profile",
    anchorId: "profile-email",
    labelKey: "search.profileEmail",
    keywords: [
      "почта",
      "e-mail",
      "email",
      "mail",
      "адрес",
      "noreply",
      "no-reply",
      "github",
      "автор",
    ],
  },

  // ── Компилятор ───────────────────────────────────────────────
  {
    sectionId: "compiler",
    anchorId: "compiler",
    labelKey: "search.compiler",
    keywords: ["latexmk", "сборка", "compile", "tex"],
  },
  {
    sectionId: "compiler",
    anchorId: "compiler-engine",
    labelKey: "search.compilerEngine",
    keywords: ["xelatex", "lualatex", "pdflatex", "движок", "engine"],
  },
  {
    sectionId: "compiler",
    anchorId: "compiler-passes",
    labelKey: "search.compilerPasses",
    keywords: [
      "проходы",
      "passes",
      "итерации",
      "latexmk",
      "сходимость",
      "оглавление",
      "ссылки",
    ],
  },
  {
    sectionId: "compiler",
    anchorId: "compiler-images",
    labelKey: "search.compilerImages",
    keywords: [
      "docker",
      "образ",
      "image",
      "tex live",
      "texlive",
      "контейнер",
      "сборка",
    ],
  },

  // ── Шрифты ───────────────────────────────────────────────────
  {
    sectionId: "fonts",
    anchorId: "fonts",
    labelKey: "search.fonts",
    keywords: [
      "шрифты",
      "шрифт",
      "fonts",
      "font",
      "times new roman",
      "consolas",
      "arial",
      "ttf",
      "otf",
      "кегль",
      "начертание",
      "глиф",
    ],
  },

  // ── Проверки ─────────────────────────────────────────────────
  {
    sectionId: "checks",
    anchorId: "checks",
    labelKey: "search.checks",
    keywords: [
      "гост",
      "методичка",
      "нормоконтроль",
      "правила",
      "проверки",
      "checks",
      "игнорировать",
    ],
  },
  {
    sectionId: "checks",
    anchorId: "checks-languagetool",
    labelKey: "search.checksLanguagetool",
    keywords: [
      "грамматика",
      "орфография",
      "стиль",
      "languagetool",
      "проверка текста",
      "docker",
      "образ",
    ],
  },

  // ── Презентации ──────────────────────────────────────────────
  {
    sectionId: "presentations",
    anchorId: "presentations",
    labelKey: "search.presentations",
    keywords: [
      "презентация",
      "слайды",
      "pptx",
      "presentation",
      "slides",
      "docker",
      "образ",
      "gotenberg",
      "onlyoffice",
    ],
  },
  {
    sectionId: "presentations",
    anchorId: "presentations-convert",
    labelKey: "search.presentationsConvert",
    keywords: [
      "gotenberg",
      "конвертер",
      "convert",
      "pdf",
      "превью",
      "preview",
      "предпросмотр",
      "pptx",
    ],
  },
  {
    sectionId: "presentations",
    anchorId: "presentations-editor",
    labelKey: "search.presentationsEditor",
    keywords: [
      "onlyoffice",
      "редактор",
      "editor",
      "слайды",
      "slides",
      "document server",
      "pptx",
    ],
  },

  // ── Провайдеры ───────────────────────────────────────────────
  {
    sectionId: "providers",
    anchorId: "providers",
    labelKey: "search.providers",
    keywords: [
      "anthropic",
      "openai",
      "claude",
      "gpt",
      "api ключ",
      "ключ",
      "api key",
      "ии",
      "ai",
      "агент",
      "provider",
    ],
  },
  {
    sectionId: "providers",
    anchorId: "providers-default-model",
    labelKey: "search.providersDefaultModel",
    keywords: ["модель по умолчанию", "default model", "агент", "выбор модели"],
  },

  // ── Локальные модели ─────────────────────────────────────────
  {
    sectionId: "local-models",
    anchorId: "local-models",
    labelKey: "search.localModels",
    keywords: [
      "ollama",
      "локальные модели",
      "оффлайн",
      "offline",
      "docker",
      "рантайм",
      "runtime",
      "gpu",
      "нативная",
      "llm",
    ],
  },

  // ── Роли агента ──────────────────────────────────────────────
  {
    sectionId: "agent-personas",
    anchorId: "agent-personas",
    labelKey: "search.agentPersonas",
    keywords: [
      "персона",
      "роль",
      "persona",
      "ассистент",
      "чат",
      "тон",
      "инструкция",
    ],
  },
  {
    sectionId: "agent-personas",
    anchorId: "agent-personas-custom",
    labelKey: "search.agentPersonasCustom",
    keywords: ["своя роль", "custom", "создать роль", "пользовательская"],
  },
  {
    sectionId: "agent-personas",
    anchorId: "agent-personas-builtin",
    labelKey: "search.agentPersonasBuiltin",
    keywords: ["встроенная", "builtin", "дублировать", "по умолчанию"],
  },

  // ── Сертификаты подписи ──────────────────────────────────────
  {
    sectionId: "signing",
    anchorId: "signing",
    labelKey: "search.signing",
    keywords: [
      "сертификат",
      "подпись",
      "pdf",
      "pades",
      "self-signed",
      "p12",
      "pfx",
      "pkcs12",
      "pkcs11",
      "удостоверение",
      "токен",
      "криптография",
    ],
  },

  // ── Диск ─────────────────────────────────────────────────────
  {
    sectionId: "disk",
    anchorId: "disk",
    labelKey: "search.disk",
    keywords: [
      "docker",
      "докер",
      "диск",
      "disk",
      "место",
      "space",
      "образы",
      "очистка",
      "cleanup",
      "кэш",
      "cache",
    ],
  },
  {
    sectionId: "disk",
    anchorId: "disk-entities",
    labelKey: "search.diskEntities",
    keywords: [
      "образы",
      "images",
      "контейнеры",
      "containers",
      "тома",
      "volumes",
      "удалить",
      "remove",
      "docker",
    ],
  },
  {
    sectionId: "disk",
    anchorId: "disk-warn-threshold",
    labelKey: "search.diskWarnThreshold",
    keywords: [
      "порог",
      "threshold",
      "предупреждение",
      "warning",
      "уведомление",
      "гб",
      "gb",
    ],
  },

  // ── Импорт / Экспорт ─────────────────────────────────────────
  {
    sectionId: "data",
    anchorId: "data-export",
    labelKey: "search.dataExport",
    keywords: [
      "экспорт",
      "export",
      "резервная копия",
      "backup",
      "скачать",
      "шифрование",
      "пароль",
    ],
  },
  {
    sectionId: "data",
    anchorId: "data-import",
    labelKey: "search.dataImport",
    keywords: [
      "импорт",
      "import",
      "загрузить",
      "восстановить",
      "слияние",
      "merge",
      "перенос",
    ],
  },

  // ── Доступ к репозиториям ────────────────────────────────────
  // ── Мои раннеры (серверный режим) ────────────────────────────
  {
    sectionId: "runners",
    anchorId: "runners",
    labelKey: "search.runners",
    keywords: [
      "раннер",
      "раннеры",
      "мои раннеры",
      "сборка на своём компьютере",
      "сборка на своем компьютере",
      "свой компьютер",
      "токен раннера",
      "runner",
      "runners",
      "my runners",
      "self-hosted",
      "build on my machine",
    ],
  },

  {
    sectionId: "git-access",
    anchorId: "git-access",
    labelKey: "search.gitAccess",
    keywords: [
      "доступ к репозиториям",
      "репозиторий",
      "синхронизация",
      "git",
      "github",
      "gitlab",
      "access",
      "repository",
      "sync",
    ],
  },
  {
    sectionId: "git-access",
    anchorId: "git-access-credentials",
    labelKey: "search.gitAccessCredentials",
    keywords: [
      "токен",
      "token",
      "pat",
      "ключ",
      "ssh",
      "key",
      "пароль",
      "password",
      "deploy key",
      "заменить токен",
      "удалить доступ",
    ],
  },
  {
    sectionId: "git-access",
    anchorId: "git-access-servers",
    labelKey: "search.gitAccessServers",
    keywords: [
      "серверы git",
      "git servers",
      "тип сервера",
      "provider",
      "провайдер",
      "gitlab",
      "gitea",
      "self-hosted",
      "свой сервер",
      "сертификат",
      "certificate",
      "ca",
      "tls",
      "https",
      "срок токена",
      "token expiry",
    ],
  },
  {
    sectionId: "git-access",
    anchorId: "git-access-hosts",
    labelKey: "search.gitAccessHosts",
    keywords: [
      "сервер",
      "server",
      "отпечаток",
      "fingerprint",
      "known hosts",
      "known_hosts",
      "ключ сервера",
      "host key",
      "забыть сервер",
    ],
  },
  {
    sectionId: "git-access",
    anchorId: "git-access-encryption",
    labelKey: "search.gitAccessEncryption",
    keywords: [
      "шифрование",
      "encryption",
      "секреты",
      "secrets",
      "ключ шифрования",
      "master key",
      "облачный диск",
      "yandex",
      "dropbox",
    ],
  },
  {
    sectionId: "git-access",
    anchorId: "git-access-fetch",
    labelKey: "search.gitAccessFetch",
    keywords: [
      "фоновая проверка",
      "background",
      "fetch",
      "интервал",
      "interval",
      "автопроверка",
      "обновления репозитория",
    ],
  },

  // ── О программе ──────────────────────────────────────────────
  {
    sectionId: "about",
    anchorId: "about",
    labelKey: "search.about",
    keywords: ["версия", "лицензия", "license", "about", "hse studio"],
  },
  {
    sectionId: "about",
    anchorId: "about-mode",
    labelKey: "search.aboutMode",
    keywords: [
      "all-in-one",
      "standard",
      "native",
      "контейнер",
      "deployment",
      "режим",
    ],
  },
  {
    sectionId: "about",
    anchorId: "about-image",
    labelKey: "search.aboutImage",
    keywords: ["образ", "image", "docker"],
  },
  {
    sectionId: "about",
    anchorId: "about-source",
    labelKey: "search.aboutSource",
    keywords: ["github", "исходники", "source", "репозиторий"],
  },
  {
    sectionId: "about",
    anchorId: "about-data-dir",
    labelKey: "search.aboutDataDir",
    keywords: ["папка", "конфигурация", "данные", "data dir", "путь", "config"],
  },
  {
    sectionId: "about",
    anchorId: "about-updates",
    labelKey: "search.aboutUpdates",
    keywords: [
      "обновление",
      "update",
      "версия",
      "что нового",
      "changelog",
      "проверить",
    ],
  },
];
