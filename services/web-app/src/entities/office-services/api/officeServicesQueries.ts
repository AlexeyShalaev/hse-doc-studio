import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  officeServicesApi,
  type OfficeServiceId,
  type OfficeServiceImages,
  type OfficeServiceRemoteTags,
  type OfficeServicesStatus,
  type SetActiveOfficeServiceImage,
} from "./officeServicesApi";

export const officeServicesKeys = {
  all: ["office-services"] as const,
  status: () => [...officeServicesKeys.all, "status"] as const,
  images: (service: string) =>
    [...officeServicesKeys.all, "images", service] as const,
  remoteTags: (service: string) =>
    [...officeServicesKeys.all, "remote-tags", service] as const,
};

export const useOfficeServicesStatus = () =>
  useQuery<OfficeServicesStatus>({
    queryKey: officeServicesKeys.status(),
    queryFn: () => officeServicesApi.status(),
    staleTime: 5_000,
  });

export const useOfficeServiceImages = (service: OfficeServiceId) =>
  useQuery<OfficeServiceImages>({
    queryKey: officeServicesKeys.images(service),
    queryFn: () => officeServicesApi.images(service),
    staleTime: 5_000,
  });

export const useOfficeServiceRemoteTags = (service: OfficeServiceId | null) =>
  useQuery<OfficeServiceRemoteTags>({
    queryKey: officeServicesKeys.remoteTags(service ?? ""),
    queryFn: () => officeServicesApi.listRemoteTags(service!),
    enabled: service !== null,
    // Docker Hub tag lists don't churn — cache 5 min so reopening the block
    // doesn't refetch, while a manual refresh still works.
    staleTime: 5 * 60_000,
  });

export const useInvalidateOfficeServices = () => {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({
      queryKey: officeServicesKeys.status(),
    });
    for (const service of ["convert", "editor"]) {
      void queryClient.invalidateQueries({
        queryKey: officeServicesKeys.images(service),
      });
    }
  };
};

export const useSetActiveOfficeServiceImage = (service: OfficeServiceId) => {
  const queryClient = useQueryClient();
  return useMutation<SetActiveOfficeServiceImage, Error, string>({
    mutationFn: (image) => officeServicesApi.setActive(service, image),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: officeServicesKeys.all });
    },
  });
};
