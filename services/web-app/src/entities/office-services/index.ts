export {
  officeServicesApi,
  officeImageRef,
  officeImageRepo,
  OFFICE_SERVICES,
  OfficeServiceContainerSchema,
  OfficeServiceStatusSchema,
  OfficeServicesStatusSchema,
  OfficeServiceImageSchema,
  OfficeServiceImagesSchema,
  OfficeServiceRemoteTagSchema,
  OfficeServiceRemoteTagsSchema,
  SetActiveOfficeServiceImageSchema,
} from "./api/officeServicesApi";
export type {
  OfficeServiceId,
  OfficeServiceContainer,
  OfficeServiceStatus,
  OfficeServicesStatus,
  OfficeServiceImage,
  OfficeServiceImages,
  OfficeServiceRemoteTag,
  OfficeServiceRemoteTags,
  SetActiveOfficeServiceImage,
} from "./api/officeServicesApi";
export {
  officeServicesKeys,
  useOfficeServicesStatus,
  useOfficeServiceImages,
  useOfficeServiceRemoteTags,
  useInvalidateOfficeServices,
  useSetActiveOfficeServiceImage,
} from "./api/officeServicesQueries";
