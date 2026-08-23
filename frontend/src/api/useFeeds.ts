import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { buildQueryString, request } from './client';
import type {
  DeleteResponse,
  FeedQueryParams,
  FeedSource,
  FeedSourceCreate,
  FeedSourceUpdate,
} from './types';

export async function fetchFeeds(params?: FeedQueryParams): Promise<FeedSource[]> {
  const qs = buildQueryString(params);
  return request<FeedSource[]>(`/api/feeds${qs}`);
}

export async function fetchFeed(id: number): Promise<FeedSource> {
  return request<FeedSource>(`/api/feeds/${id}`);
}

export async function createFeed(feed: FeedSourceCreate): Promise<FeedSource> {
  return request<FeedSource>('/api/feeds', {
    method: 'POST',
    body: JSON.stringify(feed),
  });
}

export async function updateFeed(id: number, feed: FeedSourceUpdate): Promise<FeedSource> {
  return request<FeedSource>(`/api/feeds/${id}`, {
    method: 'PUT',
    body: JSON.stringify(feed),
  });
}

export async function deleteFeed(id: number): Promise<DeleteResponse> {
  return request<DeleteResponse>(`/api/feeds/${id}`, {
    method: 'DELETE',
  });
}

export async function pollSingleFeed(id: number): Promise<any> {
  return request<any>(`/api/feeds/${id}/poll`, {
    method: 'POST',
  });
}

export async function pollAllFeeds(): Promise<any> {
  return request<any>('/api/feeds/poll-all', {
    method: 'POST',
  });
}

export function useFeedsQuery(params?: FeedQueryParams) {
  return useQuery({
    queryKey: params ? ['feeds', params] : ['feeds'],
    queryFn: () => fetchFeeds(params),
  });
}

export function useFeedQuery(id: number) {
  return useQuery({
    queryKey: ['feeds', id],
    queryFn: () => fetchFeed(id),
    enabled: !!id,
  });
}

export function useCreateFeedMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (feed: FeedSourceCreate) => createFeed(feed),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
    },
  });
}

export function useUpdateFeedMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: FeedSourceUpdate }) => updateFeed(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
    },
  });
}

export function useDeleteFeedMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteFeed(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
    },
  });
}

export function usePollSingleFeedMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => pollSingleFeed(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      queryClient.invalidateQueries({ queryKey: ['queue'] });
      queryClient.invalidateQueries({ queryKey: ['history'] });
    },
  });
}

export function usePollAllFeedsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => pollAllFeeds(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      queryClient.invalidateQueries({ queryKey: ['queue'] });
      queryClient.invalidateQueries({ queryKey: ['history'] });
    },
  });
}
