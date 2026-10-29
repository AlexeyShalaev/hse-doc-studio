import { useEffect, useState } from "react";
import { Route, Routes } from "react-router";
import { Spinner } from "@shared/ui";
import { loadAdminLocales } from "./adminLocales";
import { AdminLayout } from "./AdminLayout";
import { AdminOverview, AdminSectionSoon } from "./AdminSections";

// Метка для verify:admin-chunk: этой строки не должно быть ни в entry, ни в
// auth-чанках. Она лежит в коде чанка, а не в словарях.
export const ADMIN_CHUNK_MARKER = "hse-admin-chunk-marker";

/**
 * Корень админки (маршрут /admin/*). Единственная точка входа lazy-чанка:
 * подключает словари admin/ и рисует разделы. Права проверяет охранник
 * снаружи, чанк запрашивается только после него.
 */
export const AdminApp = () => {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let live = true;
    void loadAdminLocales().then(() => {
      if (live) setReady(true);
    });
    return () => {
      live = false;
    };
  }, []);

  if (!ready) {
    return (
      <div
        className="flex flex-1 items-center justify-center"
        data-testid={ADMIN_CHUNK_MARKER}
        role="status"
        aria-label="admin"
      >
        <Spinner size="lg" />
      </div>
    );
  }
  return (
    <Routes>
      <Route element={<AdminLayout />}>
        <Route index element={<AdminOverview />} />
        <Route path=":section" element={<AdminSectionSoon />} />
      </Route>
    </Routes>
  );
};
