export interface WatchlistItem {
  id: number;
  app_name: string;
  package_name?: string | null;
  title_regex?: string | null;
  min_version?: string | null;
  releaser_whitelist: string[];
  releaser_blacklist: string[];
  category: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface WatchlistItemCreate {
  app_name: string;
  package_name?: string | null;
  title_regex?: string | null;
  min_version?: string | null;
  releaser_whitelist?: string[];
  releaser_blacklist?: string[];
  category?: string;
  enabled?: boolean;
}

export interface WatchlistItemUpdate {
  app_name?: string;
  package_name?: string | null;
  title_regex?: string | null;
  min_version?: string | null;
  releaser_whitelist?: string[];
  releaser_blacklist?: string[];
  category?: string;
  enabled?: boolean;
}

export interface WatchlistQueryParams {
  enabled?: boolean;
  category?: string;
  query?: string;
  limit?: number;
  offset?: number;
}

export interface FeedSource {
  id: number;
  name: string;
  url: string;
  feed_type: string;
  enabled: boolean;
  poll_interval_minutes: number;
  last_polled_at?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface FeedSourceCreate {
  name: string;
  url: string;
  feed_type?: string;
  enabled?: boolean;
  poll_interval_minutes?: number;
}

export interface FeedSourceUpdate {
  name?: string;
  url?: string;
  feed_type?: string;
  enabled?: boolean;
  poll_interval_minutes?: number;
}

export interface FeedQueryParams {
  enabled?: boolean;
}

export type ResolverTier = 'real_debrid' | 'alldebrid' | 'jdownloader' | 'direct';

export interface DownloadTask {
  id: number;
  watchlist_item_id?: number | null;
  feed_item_title: string;
  feed_item_url?: string | null;
  matched_version?: string | null;
  matched_releaser?: string | null;
  status: 'pending' | 'resolving' | 'downloading' | 'completed' | 'failed' | string;
  download_tier?: ResolverTier | null | string;
  mirror_urls?: string[];
  resolved_url?: string | null;
  file_path?: string | null;
  file_size?: number | null;
  error_message?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
}

export interface QueueQueryParams {
  status?: string;
  limit?: number;
  offset?: number;
}

export interface DownloadHistory {
  id: number;
  task_id?: number | null;
  app_name: string;
  version?: string | null;
  releaser?: string | null;
  target_path?: string | null;
  file_size?: number | null;
  duration_seconds?: number | null;
  download_tier?: string | null;
  status: string;
  downloaded_at?: string | null;
}

export interface HistoryQueryParams {
  status?: string;
  query?: string;
  limit?: number;
  offset?: number;
}

export interface ManualDownloadRequest {
  url: string;
  app_name?: string;
  version?: string;
  releaser?: string;
  category?: string;
  auto_resolve?: boolean;
  trigger_ingest?: boolean;
  download_tier?: string;
}

export interface AppSettings {
  app_name: string;
  host?: string;
  port?: number;
  debug: boolean;
  database_url?: string;
  download_dir: string;
  staging_dir: string;
  poll_interval_seconds: number;
  real_debrid_api_token: string;
  alldebrid_api_key?: string;
  alldebrid_agent?: string;
  jdownloader_email: string;
  jdownloader_password?: string;
  jdownloader_device_name: string;
  jdownloader_watch_dir: string;
  scraper_url: string;
  nextcloud_url: string;
  nextcloud_token?: string;
  nextcloud_occ_command: string;
  apprise_url: string;
  ntfy_topic: string;
  [key: string]: any;
}

export interface SettingsUpdateRequest {
  app_name?: string;
  debug?: boolean;
  download_dir?: string;
  staging_dir?: string;
  poll_interval_seconds?: number;
  real_debrid_api_token?: string;
  alldebrid_api_key?: string;
  alldebrid_agent?: string;
  jdownloader_email?: string;
  jdownloader_password?: string;
  jdownloader_device_name?: string;
  jdownloader_watch_dir?: string;
  scraper_url?: string;
  nextcloud_url?: string;
  nextcloud_token?: string;
  nextcloud_occ_command?: string;
  apprise_url?: string;
  ntfy_topic?: string;
  [key: string]: any;
}

export interface HealthStatus {
  status: string;
  version: string;
  timestamp?: string;
  active_tasks?: number;
}

export interface DeleteResponse {
  status: string;
  id: number;
  app_name?: string;
  name?: string;
  title?: string;
}
