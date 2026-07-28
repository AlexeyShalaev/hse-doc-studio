import { useState } from "react";
import { useTranslation } from "react-i18next";
import { GraduationCap } from "lucide-react";

import type { HsePersonFields } from "../lib";
import { HsePersonLookupModal } from "./HsePersonLookupModal";

export type HsePersonLookupButtonProps = {
  onSelect: (fields: HsePersonFields) => void;
  // Prefill the search box (e.g. the name already typed into the field).
  initialQuery?: string;
  className?: string;
};

export const HsePersonLookupButton = ({
  onSelect,
  initialQuery,
  className,
}: HsePersonLookupButtonProps) => {
  const { t } = useTranslation("hsePerson");
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        className={className ?? "btn xs ghost"}
        onClick={() => {
          setOpen(true);
        }}
      >
        <GraduationCap size={12} />
        {t("button")}
      </button>
      {open && (
        <HsePersonLookupModal
          isOpen={open}
          onClose={() => {
            setOpen(false);
          }}
          onSelect={onSelect}
          initialQuery={initialQuery ?? ""}
        />
      )}
    </>
  );
};
