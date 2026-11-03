export * from "./model/device.schema";
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
