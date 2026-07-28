import { useEffect, useRef } from "react";

/**
 * Полный набор глобальных сочетаний верстака. Экран передаёт только то, что
 * для него осмысленно (на Welcome нет проекта — нет и «собрать всё»), поэтому
 * хук принимает Partial: непереданная комбинация не перехватывается вообще и
 * достаётся браузеру.
 */
export type GlobalHotkeyHandlers = {
  onTogglePalette: () => void;
  onToggleSidebar: () => void;
  onToggleDock: () => void;
  onOpenIssues: () => void;
  onSelectDocuments: () => void;
  onSelectFiles: () => void;
  onSelectSubmit: () => void;
  onBuildAll: () => void;
  onOpenProjectSwitcher: () => void;
  onNewProject: () => void;
  onOpenSettings: () => void;
  onFocusFilter: () => void;
};

type HotkeyName = keyof GlobalHotkeyHandlers;

// Платформа определяется один раз на модуль: на mac модификатор — ⌘, на всём
// остальном — Ctrl. userAgent, а не устаревший navigator.platform.
const IS_MAC = /mac|iphone|ipad|ipod/i.test(navigator.userAgent);

/**
 * Ввод текста съедает «голые» символьные шорткаты: поле, textarea, select,
 * contenteditable и всё, что внутри CodeMirror (там «/» — обычный символ
 * LaTeX-исходника, а не «сфокусировать фильтр»).
 */
const isTypingTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return target.closest(".cm-editor") !== null;
};

/** Нажат «наш» модификатор и при этом не нажат чужой (и не Alt/AltGr). */
const isModPressed = (event: KeyboardEvent): boolean => {
  const mod = IS_MAC ? event.metaKey : event.ctrlKey;
  const foreign = IS_MAC ? event.ctrlKey : event.metaKey;
  return mod && !foreign && !event.altKey;
};

/**
 * Символ комбинации по физической клавише: в кириллической раскладке ⌘+K
 * приходит как e.key === "к", поэтому для буквенных клавиш опираемся на
 * e.code и откатываемся на e.key, когда code недоступен (jsdom, экранные
 * клавиатуры).
 */
const hotkeyChar = (event: KeyboardEvent): string => {
  const code = event.code;
  if (code.length === 4 && code.startsWith("Key")) {
    return code.charAt(3).toLowerCase();
  }
  if (code === "Comma") return ",";
  return event.key.toLowerCase();
};

const MOD_SHIFT_KEYS: Record<string, HotkeyName> = {
  m: "onOpenIssues",
  e: "onSelectDocuments",
  f: "onSelectFiles",
  d: "onSelectSubmit",
  b: "onBuildAll",
};

const MOD_KEYS: Record<string, HotkeyName> = {
  k: "onTogglePalette",
  b: "onToggleSidebar",
  j: "onToggleDock",
  p: "onOpenProjectSwitcher",
  n: "onNewProject",
  ",": "onOpenSettings",
};

const resolveHotkey = (event: KeyboardEvent): HotkeyName | null => {
  if (!isModPressed(event)) {
    // «/» без модификаторов. Shift не проверяем: в русской раскладке «/» и
    // берётся с Shift, а e.key уже говорит, какой символ реально введён.
    if (
      event.key === "/" &&
      !event.altKey &&
      !event.ctrlKey &&
      !event.metaKey
    ) {
      return "onFocusFilter";
    }
    return null;
  }
  const char = hotkeyChar(event);
  const table = event.shiftKey ? MOD_SHIFT_KEYS : MOD_KEYS;
  return table[char] ?? null;
};

/**
 * Единственный регистратор глобальных клавиш. Один слушатель на window,
 * обработчики живут в ref — инлайновые стрелки в вызывающем коде не
 * перевешивают слушатель на каждый рендер.
 *
 * Намеренно НЕ занимаем ⌘W, ⌘⇧T и ⌘1..9: приложение живёт во вкладке
 * браузера, и эти сочетания принадлежат ей.
 */
export const useGlobalHotkeys = (
  handlers: Partial<GlobalHotkeyHandlers>,
): void => {
  const handlersRef = useRef(handlers);

  useEffect(() => {
    handlersRef.current = handlers;
  });

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent): void => {
      const name = resolveHotkey(event);
      if (name === null) return;
      // Модификаторные сочетания работают и в поле ввода (⌘K из фильтра —
      // норма), символьные — нет.
      if (name === "onFocusFilter" && isTypingTarget(event.target)) return;

      // ⌘P гасим всегда: печать страницы верстака бессмысленна (PDF печатают
      // из просмотрщика), а браузерный диалог перекрывает интерфейс.
      if (name === "onOpenProjectSwitcher") event.preventDefault();

      const handler = handlersRef.current[name];
      // Остальные незанятые комбинации уходят браузеру нетронутыми.
      if (handler === undefined) return;

      // Дефолт гасим до вызова: обработчик может бросить, а перехват уже нужен.
      event.preventDefault();
      handler();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);
};
