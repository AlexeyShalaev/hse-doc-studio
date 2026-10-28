export { SetupWizard } from "./ui/SetupWizard";
export type { SetupWizardProps } from "./ui/SetupWizard";
export { SetupShell } from "./ui/SetupShell";
export { LanguageStep } from "./ui/LanguageStep";
export { AdminStep } from "./ui/AdminStep";
export { RegistrationStep } from "./ui/RegistrationStep";
export { SignInStep } from "./ui/SignInStep";
export { EnvironmentStep } from "./ui/EnvironmentStep";
export { DoneStep } from "./ui/DoneStep";
export { OccupiedCard } from "./ui/OccupiedCard";
export {
  SETUP_STEPS,
  environmentVerdict,
  isOccupied,
  nextStep,
  parseDomains,
  prevStep,
  resumeStep,
} from "./lib/steps";
export type { SetupStepId, SettingsDraft } from "./lib/steps";
export { SETUP_ERROR_CODES, setupErrorKey } from "./lib/setupErrors";
export { getServerSetupGallery } from "./ui/setupGallery";
