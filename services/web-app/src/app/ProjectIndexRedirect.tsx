import { Navigate, useParams } from "react-router";
import { getLastDoc } from "@shared/lib";

/**
 * Возврат в контекст: вход в проект открывает документ, на котором пользователь
 * остановился в прошлый раз. Без памяти (первый заход, приватный режим) —
 * обычный экран документов проекта.
 *
 * Запомненный id намеренно не сверяется с составом проекта: документ мог
 * исчезнуть вместе с обновлением пакета. Тогда рабочая область покажет пустое
 * состояние, а нав слева даст выбрать другой — это дешевле, чем задерживать
 * редирект до загрузки списка документов.
 */
export const ProjectIndexRedirect = () => {
  const { projectId = "" } = useParams<{ projectId: string }>();
  const lastDocId = getLastDoc(projectId);
  const base = `/projects/${projectId}/documents`;

  return <Navigate to={lastDocId ? `${base}/${lastDocId}` : base} replace />;
};
