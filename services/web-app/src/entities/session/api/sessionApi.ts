import { ApiError, apiClient, parseResp, setCsrfToken } from "@shared/api";
import { BootstrapSchema, type Bootstrap } from "./schemas";

/**
 * Ответ для бэкенда без ручки bootstrap (локальный режим, пока сервер её не
 * отдаёт): локальные возможности включены, пользователя нет. Приложение
 * работает как раньше, а решения «что показать» принимаются по capabilities.
 */
export const LOCAL_BOOTSTRAP: Bootstrap = {
  mode: "local",
  version: "",
  setup_state: "ready",
  auth: {
    registration_mode: "closed",
    password_enabled: false,
    oidc_providers: [],
    smtp_enabled: false,
    password_min_length: 10,
  },
  user: null,
  capabilities: {
    fs_browse: true,
    connect_folder: true,
    open_in_editor: true,
    move_project: true,
    docker_ui: true,
    self_update: true,
    local_services_ui: true,
    admin: false,
    personal_signing_keys: false,
  },
  csrf_token: null,
};

export const sessionApi = {
  /**
   * Единый вход в состояние сессии. CSRF-токен кладётся в транспорт тут же,
   * чтобы любой следующий небезопасный запрос уже нёс его.
   */
  bootstrap: async (): Promise<Bootstrap> => {
    try {
      const data = await apiClient
        .get("/session/bootstrap", { silentError: true })
        .then(parseResp(BootstrapSchema));
      setCsrfToken(data.csrf_token);
      return data;
    } catch (error) {
      // Бэкенд без этой ручки это локальный режим: работаем как раньше.
      if (error instanceof ApiError && error.status === 404) {
        setCsrfToken(null);
        return LOCAL_BOOTSTRAP;
      }
      throw error;
    }
  },
};
