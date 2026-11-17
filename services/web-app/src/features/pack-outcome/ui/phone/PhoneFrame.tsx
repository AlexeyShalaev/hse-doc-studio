import type { ReactNode } from "react";
import { useIsPhoneWidth } from "@shared/lib";

/** Рамка телефона: узкое окно с самой галереей, если окно браузера шире телефона. */
export const PhoneFrame = ({
  id,
  children,
}: {
  id: string;
  children: ReactNode;
}) => {
  const phone = useIsPhoneWidth();
  if (phone) return <>{children}</>;
  return (
    <iframe
      title={id}
      src={`/dev/server-screens?section=pack-studio&entry=${id}`}
      style={{
        width: 360,
        height: 720,
        border: "1px solid var(--border)",
        borderRadius: "0.5rem",
        background: "var(--bg-0)",
      }}
    />
  );
};
