import { configure } from "@testing-library/react";

// Подключается только проектом studio-heavy (vitest.config.ts). Ожидания findBy*/waitFor ждут
// до 10 с вместо 1 с по умолчанию: на медленном раннере дерево экрана доезжает позже. Проверка та же,
// быстрый тест не замедляется, дольше ждёт лишь тот, что и так упал бы.
configure({ asyncUtilTimeout: 10_000 });
