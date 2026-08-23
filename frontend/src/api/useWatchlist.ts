import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { buildQueryString, request } from './client';
import type {
  DeleteResponse,
  WatchlistItem,
  WatchlistItemCreate,
  WatchlistItemUpdate,
  WatchlistQueryParams,
} from './types';

export async function fetchWatchlist(params?: WatchlistQueryParams): Promise<WatchlistItem[]> {
  const qs = buildQueryString(params);
  return request<WatchlistItem[]>(`/api/watchlist${qs}`);
}

export async function fetchWatchlistItem(id: number): Promise<WatchlistItem> {
  return request<WatchlistItem>(`/api/watchlist/${id}`);
}

export async function createWatchlistItem(item: WatchlistItemCreate): Promise<WatchlistItem> {
  return request<WatchlistItem>('/api/watchlist', {
    method: 'POST',
    body: JSON.stringify(item),
  });
}

export async function updateWatchlistItem(
  id: number,
  item: WatchlistItemUpdate
): Promise<WatchlistItem> {
  return request<WatchlistItem>(`/api/watchlist/${id}`, {
    method: 'PUT',
    body: JSON.stringify(item),
  });
}

export async function deleteWatchlistItem(id: number): Promise<DeleteResponse> {
  return request<DeleteResponse>(`/api/watchlist/${id}`, {
    method: 'DELETE',
  });
}

export function useWatchlistQuery(params?: WatchlistQueryParams) {
  return useQuery({
    queryKey: params ? ['watchlist', params] : ['watchlist'],
    queryFn: () => fetchWatchlist(params),
  });
}

export function useWatchlistItemQuery(id: number) {
  return useQuery({
    queryKey: ['watchlist', id],
    queryFn: () => fetchWatchlistItem(id),
    enabled: !!id,
  });
}

export function useCreateWatchlistMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (item: WatchlistItemCreate) => createWatchlistItem(item),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
    },
  });
}

export function useUpdateWatchlistMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: WatchlistItemUpdate }) =>
      updateWatchlistItem(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
    },
  });
}

export function useDeleteWatchlistMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteWatchlistItem(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
    },
  });
}

export function useToggleWatchlistMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      updateWatchlistItem(id, { enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
    },
  });
}
