export * from "./model/device.schema";
export * from "./model/people.schema";
export { usePlaceStore } from "./model/placeStore";
export { peopleApi } from "./api/peopleApi";
export { nudgePeople, peopleKeys, useProjectPeople } from "./api/peopleQueries";
export type { Place } from "./api/peopleQueries";
export {
  DEFAULT_INTERVAL_S,
  MAX_AVATARS,
  MIN_SIGNAL_GAP_MS,
  PLACE_DEBOUNCE_MS,
  deviceKind,
  hasDocument,
  pickPeople,
  splitPeople,
  tabSessionId,
} from "./lib/peopleLib";
export type { DeviceKind, DocActivity, VisiblePeople } from "./lib/peopleLib";
export { deviceApi, studioLinkApi } from "./api/deviceApi";
export {
  PRESENCE_POLL_MS,
  deviceKeys,
  useAccountDevices,
  useForgetDevice,
  useLocalDevice,
  useProjectStudios,
  useRenameDevice,
  useStudioLink,
} from "./api/deviceQueries";
export {
  ACTIVITY_KEY,
  AI_DOT,
  AI_NEEDS_ACTION,
  RUNNER_DOT,
  SYNC_DOT,
  cloudSeesOnline,
  firstUnprovidedEndpoint,
  isServerReachable,
  presenceDot,
  secondsSince,
} from "./lib/deviceLib";
export {
  commitsText,
  modelNames,
  modelsText,
  presenceText,
} from "./lib/deviceText";
export { AiAdvice, DeviceCard, EndpointCloudState } from "./ui";
export type { DeviceCardProps, EndpointCloudStateProps } from "./ui";
