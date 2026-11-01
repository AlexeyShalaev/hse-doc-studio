import { Spinner } from "@shared/ui";

/** Ожидание чанка раздела админки; подпись «Загрузка» даёт сам Spinner. */
export const AdminChunkLoading = ({
  size = "md",
  testId,
}: {
  size?: "md" | "lg";
  testId?: string;
}) => (
  <div
    className={`flex items-center justify-center${size === "lg" ? " flex-1" : ""}`}
    data-testid={testId}
  >
    <Spinner size={size} />
  </div>
);
