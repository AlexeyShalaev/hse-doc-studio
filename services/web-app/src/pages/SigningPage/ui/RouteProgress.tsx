import { useTranslation } from "react-i18next";
import type { SigningTask, SigningTaskPerson } from "@entities/signing-route";
import { usePersonaLabel } from "@features/signing-route-progress";

type Tone = "ok" | "now" | "warn" | "idle";

/** Как назвать состояние человека в строке хода: `waiting` с временем значит «согласовано». */
const stateKey = (person: SigningTaskPerson): string =>
  person.state === "waiting" && person.at ? "approved" : person.state;

const toneOf = (person: SigningTaskPerson): Tone => {
  switch (person.state) {
    case "done":
      return "ok";
    case "to_approve":
    case "to_approve_sign":
    case "to_sign":
      return "now";
    case "returned":
      return "warn";
    case "waiting":
      return person.at ? "ok" : "idle";
    case "invited":
      return "idle";
  }
};

/** Ход маршрута одной строкой: «1. Иванов И.: готово · 2. Вы: согласует · 3. Сидоров С.: ждёт». */
export const RouteProgress = ({ task }: { task: SigningTask }) => {
  const { t, i18n } = useTranslation("signing");
  const personaLabel = usePersonaLabel();
  // Роль в подсказке с заглавной: «Научный руководитель»; неизвестная персона как есть.
  const role = (persona: string): string => {
    const label = personaLabel(persona);
    return label === null
      ? persona
      : label.charAt(0).toLocaleUpperCase(i18n.language) + label.slice(1);
  };
  return (
    <section aria-label={t("progress.title")} data-testid="signing-progress">
      <ol className="sgn-steps">
        {task.steps.map((step, index) => (
          <li
            key={index}
            className="sgn-step"
            aria-label={t("progress.step", { n: index + 1 })}
            data-current={task.route.current_step === index + 1}
          >
            <span className="sgn-step-num">{index + 1}.</span>
            {step.map((person, i) => (
              <span
                key={`${person.persona}-${String(i)}`}
                className="sgn-person"
                data-me={person.me}
                data-tone={toneOf(person)}
                data-state={person.state}
                title={role(person.persona)}
              >
                <span className="sgn-person-name">
                  {person.me
                    ? t("progress.you")
                    : (person.name ?? t("progress.nobody"))}
                </span>
                <span className="sgn-person-state">
                  {/* Себе другие слова: «Вы: ваша очередь», а не «Вы согласует». */}
                  {/* Где слова совпадают, своих в `mine` нет: берутся из `state`. */}
                  {t([
                    ...(person.me ? [`progress.mine.${stateKey(person)}`] : []),
                    `progress.state.${stateKey(person)}`,
                  ])}
                </span>
              </span>
            ))}
          </li>
        ))}
      </ol>
    </section>
  );
};
