import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { buildQueryString, request } from './client';
import type {
  DeleteResponse,
  DownloadHistory,
  DownloadTask,
  HistoryQueryParams,
  ManualDownloadRequest,
  QueueQueryParams,
} from './types';

export async function fetchQueue(params?: QueueQueryParams): Promise<DownloadTask[]> {
  const qs = buildQueryString(params);
  return request<DownloadTask[]>(`/api/downloads/queue${qs}`);
}

export async function fetchHistory(params?: HistoryQueryParams): Promise<DownloadHistory[]> {
  const qs = buildQueryString(params);
  return request<DownloadHistory[]>(`/api/downloads/history${qs}`);
}

export async function manualDownload(req: ManualDownloadRequest): Promise<DownloadTask> {
  return request<DownloadTask>('/api/downloads/manual', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function retryDownload(taskId: number): Promise<DownloadTask> {
  return request<DownloadTask>(`/api/downloads/${taskId}/retry`, {
    method: 'POST',
  });
}

export async function cancelDownload(taskId: number): Promise<DeleteResponse> {
  return request<DeleteResponse>(`/api/downloads/${taskId}`, {
    method: 'DELETE',
  });
}

export function useQueueQuery(pollingIntervalMs?: number, params?: QueueQueryParams) {
  return useQuery({
    queryKey: params ? ['queue', params] : ['queue'],
    queryFn: () => fetchQueue(params),
    refetchInterval: pollingIntervalMs && pollingIntervalMs > 0 ? pollingIntervalMs : false,
  });
}

export function useHistoryQuery(params?: HistoryQueryParams) {
  return useQuery({
    queryKey: params ? ['history', params] : ['history'],
    queryFn: () => fetchHistory(params),
  });
}

export function useManualDownloadMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: ManualDownloadRequest) => manualDownload(req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] });
      queryClient.invalidateQueries({ queryKey: ['history'] });
      queryClient.invalidateQueries({ queryKey: ['system-status'] });
    },
  });
}

export function useRetryDownloadMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: number) => retryDownload(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] });
      queryClient.invalidateQueries({ queryKey: ['history'] });
    },
  });
}

export function useCancelDownloadMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: number) => cancelDownload(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] });
      queryClient.invalidateQueries({ queryKey: ['history'] });
    },
  });
}
