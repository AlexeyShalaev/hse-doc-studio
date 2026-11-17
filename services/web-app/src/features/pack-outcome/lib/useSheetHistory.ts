import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";
import { outcomeUrlWrites } from "./urlState";

// Лист или окно на телефоне закрывается кнопкой «Назад» браузера: открытие добавляет запись в
// историю (тот же адрес, метка в состоянии), «Назад» её снимает, а лист читает это как закрытие.
// Закрытие кнопкой, Esc или по фону делает шаг назад само, чтобы запись не осталась мёртвой.
// Листы вкладываются (окно сценария поверх «Параметров»): метка хранит стопку идентификаторов.

type Mark = { poSheet: string[] };

const stackOf = (state: unknown): string[] => {
  if (typeof state !== "object" || state === null) return [];
  const stack = (state as Partial<Mark>).poSheet;
  return Array.isArray(stack) ? stack : [];
};

/**
 * Привязывает открытый лист к истории браузера. `open` включается только на телефоне; `id`
 * отличает листы друг от друга; `close` закрывает лист (зовётся и при «Назад»).
 */
export const useSheetHistory = (
  id: string,
  open: boolean,
  close: () => void,
): void => {
  const navigate = useNavigate();
  const location = useLocation();
  const stack = stackOf(location.state);
  const active = stack.includes(id);
  const pushed = useRef(false);
  const writesAtOpen = useRef(0);
  const closeRef = useRef(close);
  const here = useRef(location);
  useEffect(() => {
    closeRef.current = close;
    here.current = location;
  });
  const { pathname, search, hash } = location;

  // Открытие: добавить запись с меткой поверх стопки.
  useEffect(() => {
    if (!open || pushed.current) return;
    pushed.current = true;
    writesAtOpen.current = outcomeUrlWrites();
    void navigate(
      { pathname, search, hash },
      { state: { poSheet: [...stack, id] } },
    );
  }, [hash, id, navigate, open, pathname, search, stack]);

  // «Назад» сняло метку, пока лист открыт: закрыть лист.
  const wasActive = useRef(false);
  useEffect(() => {
    if (open && wasActive.current && !active) {
      pushed.current = false;
      closeRef.current();
    }
    wasActive.current = open && active;
  }, [active, open]);

  // Закрыли сами (кнопка, Esc, фон): снять запись шагом назад. Если внутри листа писали в адрес
  // экрана (выбрали сценарий), шаг назад вернул бы старый адрес: тогда запись остаётся, а метку
  // с неё снимает следующее обновление адреса (состояние роутера приходит чуть позже записи).
  const wasOpen = useRef(false);
  const stripAt = useRef<string | null>(null);
  useEffect(() => {
    if (wasOpen.current && !open && pushed.current) {
      pushed.current = false;
      const now = here.current;
      if (stackOf(now.state).at(-1) === id) {
        if (outcomeUrlWrites() === writesAtOpen.current) void navigate(-1);
        else stripAt.current = now.key;
      }
    }
    wasOpen.current = open;
  }, [id, navigate, open]);

  const { key } = location;
  useEffect(() => {
    if (stripAt.current === null || stripAt.current === key) return;
    stripAt.current = null;
    if (!active) return;
    void navigate(
      { pathname, search, hash },
      {
        replace: true,
        state: { poSheet: stack.filter((item) => item !== id) },
      },
    );
  }, [active, hash, id, key, navigate, pathname, search, stack]);
};
