/** Тон метки статуса версии: stable зелёная, beta синяя, deprecated жёлтая, прочее нейтральная. */
export const versionStatusVariant = (
  status: string,
): "ok" | "info" | "warn" | "neutral" => {
  switch (status) {
    case "stable":
      return "ok";
    case "beta":
      return "info";
    case "deprecated":
      return "warn";
    default:
      return "neutral";
  }
};
