import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request } from './client';
import type { AppSettings, HealthStatus, SettingsUpdateRequest } from './types';

export async function fetchSettings(): Promise<AppSettings> {
  return request<AppSettings>('/api/settings');
}

export async function updateSettings(settings: SettingsUpdateRequest): Promise<AppSettings> {
  return request<AppSettings>('/api/settings', {
    method: 'POST',
    body: JSON.stringify(settings),
  });
}

export async function fetchSystemStatus(): Promise<HealthStatus> {
  return request<HealthStatus>('/health');
}

export function useSettingsQuery() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  });
}

export function useUpdateSettingsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (settings: SettingsUpdateRequest) => updateSettings(settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['system-status'] });
    },
  });
}

export function useSystemStatusQuery(refetchInterval?: number) {
  return useQuery({
    queryKey: ['system-status'],
    queryFn: fetchSystemStatus,
    refetchInterval: refetchInterval && refetchInterval > 0 ? refetchInterval : false,
  });
}
