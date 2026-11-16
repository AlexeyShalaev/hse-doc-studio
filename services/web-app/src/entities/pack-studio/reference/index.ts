export {
  COURSEWORK_INPUTS,
  COURSEWORK_OUTCOME,
  COURSEWORK_RUN,
  COURSEWORK_SCENARIOS,
  VKR_BRANCHES,
  VKR_CHECKS,
  VKR_INPUTS,
  VKR_OUTCOME,
} from "./fixtures";
export { elementInfos, explainFor, realExplains } from "./explain";
export {
  REFERENCE_BEHAVIORS,
  setExplainBehavior,
  installOutcomeReference,
  outcomeReference,
  outcomeReferenceRoutes,
  scenarioReference,
} from "./routes";
export type {
  ExplainBehavior,
  ReferenceBehavior,
  ReferenceSource,
} from "./routes";
export {
  patchReferenceModel,
  referenceManifest,
  referenceModel,
  resetReferenceManifests,
  touchReferenceManifest,
} from "./manifests";
