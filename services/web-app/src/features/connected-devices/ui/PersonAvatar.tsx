import { forwardRef, type ButtonHTMLAttributes } from "react";
import { clsx } from "clsx";
import type { PersonOnline } from "@entities/connected-device";

const markStyle = (person: PersonOnline, size: number) => ({
  width: size,
  height: size,
  fontSize: Math.max(9, Math.round(size * 0.4)),
  background: person.color,
});

export type AvatarMarkProps = { person: PersonOnline; size?: number };

/**
 * Значок человека в сети: инициалы на цвете, который у его курсора в документе (цвет приходит с сервера), точка
 * «в сети». Фото профиля в системе нет, поэтому только инициалы. Свой значок с кольцом. Просто рисунок: подпись
 * и действие даёт тот, кто его использует.
 */
export const AvatarMark = ({ person, size = 24 }: AvatarMarkProps) => (
  <span
    className="pp-avatar"
    aria-hidden="true"
    data-me={person.me ? "true" : undefined}
    style={markStyle(person, size)}
  >
    <span>{person.initials}</span>
    <span className="pp-dot" />
  </span>
);

export type PersonAvatarProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "color"
> & {
  person: PersonOnline;
  size?: number;
};

/** Аватар-кнопка в шапке: тот, у кого есть документ, ведёт к нему по нажатию. */
export const PersonAvatar = forwardRef<HTMLButtonElement, PersonAvatarProps>(
  ({ person, size = 24, className, style, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      className={clsx("pp-avatar", className)}
      data-me={person.me ? "true" : undefined}
      data-testid="person-avatar"
      data-user={person.user_id}
      style={{ ...markStyle(person, size), ...style }}
      {...props}
    >
      <span aria-hidden="true">{person.initials}</span>
      <span className="pp-dot" aria-hidden="true" />
    </button>
  ),
);
PersonAvatar.displayName = "PersonAvatar";
