import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  BookmarkCheck,
  Rss,
  CheckCircle2,
  Activity,
  RefreshCw,
  Plus,
  ArrowRight,
  Radio,
  Clock,
  RotateCw,
  FileCode2,
} from 'lucide-react';
import {
  useWatchlistQuery,
  useFeedsQuery,
  useQueueQuery,
  useHistoryQuery,
  useSystemStatusQuery,
  useRetryDownloadMutation,
} from '../api';
import { useUIStore, useToastStore } from '../stores';
import { StatCard, Badge } from '../components/common';
import { ManualDownloadModal } from '../components/modals';
import { formatBytes, formatDate } from '../utils';

export const Dashboard: React.FC = () => {
  const setManualModalOpen = useUIStore((state) => state.setManualModalOpen);
  const queuePollingInterval = useUIStore((state) => state.queuePollingInterval);
  const addToast = useToastStore((state) => state.addToast);

  const [retryingTaskId, setRetryingTaskId] = useState<number | null>(null);

  // Queries
  const {
    data: watchlist = [],
    isLoading: isWatchlistLoading,
    refetch: refetchWatchlist,
  } = useWatchlistQuery();

  const {
    data: feeds = [],
    isLoading: isFeedsLoading,
    refetch: refetchFeeds,
  } = useFeedsQuery();

  const {
    data: queue = [],
    isLoading: isQueueLoading,
    refetch: refetchQueue,
  } = useQueueQuery(queuePollingInterval);

  const {
    data: history = [],
    isLoading: isHistoryLoading,
    refetch: refetchHistory,
  } = useHistoryQuery({ limit: 10 });

  const {
    data: health,
    isLoading: isHealthLoading,
    refetch: refetchHealth,
  } = useSystemStatusQuery(15000);

  const retryMutation = useRetryDownloadMutation();

  const isRefreshing =
    isWatchlistLoading || isFeedsLoading || isQueueLoading || isHistoryLoading || isHealthLoading;

  const handleRefreshAll = async () => {
    try {
      await Promise.all([
        refetchWatchlist(),
        refetchFeeds(),
        refetchQueue(),
        refetchHistory(),
        refetchHealth(),
      ]);
      addToast({
        type: 'info',
        title: 'Dashboard Refreshed',
        message: 'Updated stats and queue data',
        duration: 2500,
      });
    } catch {
      addToast({
        type: 'error',
        title: 'Refresh Error',
        message: 'Failed to update some dashboard components',
      });
    }
  };

  const handleRetryTask = async (taskId: number) => {
    setRetryingTaskId(taskId);
    try {
      await retryMutation.mutateAsync(taskId);
      addToast({
        type: 'success',
        title: 'Retry Queued',
        message: `Task #${taskId} has been re-queued for processing`,
      });
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Retry Failed',
        message: err?.message || `Failed to retry task #${taskId}`,
      });
    } finally {
      setRetryingTaskId(null);
    }
  };

  // Metric computations
  const totalWatchlist = watchlist.length;
  const activeWatchlist = watchlist.filter((item) => item.enabled).length;

  const totalFeeds = feeds.length;
  const activeFeeds = feeds.filter((feed) => feed.enabled).length;

  const completedDownloads = history.filter((h) => h.status === 'completed').length;

  const isHealthy =
    health?.status?.toLowerCase() === 'ok' || health?.status?.toLowerCase() === 'healthy';

  const recentIngests = history.slice(0, 5);

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Top Header & Quick Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white">
              Pipeline Overview
            </h1>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/15 text-indigo-400 border border-indigo-500/30 font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse shrink-0" />
              LIVE
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Autonomous monitoring, resolving, and staging APK releases.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <button
            type="button"
            onClick={handleRefreshAll}
            disabled={isRefreshing}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm font-medium bg-slate-800/80 hover:bg-slate-700/80 text-slate-200 border border-slate-700/60 transition disabled:opacity-50"
            title="Refresh all metrics and queues"
          >
            <RefreshCw className={`w-4 h-4 text-slate-400 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>

          <button
            type="button"
            onClick={() => setManualModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white shadow-lg shadow-indigo-500/25 transition transform active:scale-95"
          >
            <Plus className="w-4 h-4" />
            <span>Manual Download</span>
          </button>
        </div>
      </div>

      {/* 4 Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Active Watchlist */}
        <StatCard
          title="Active Watchlist"
          value={activeWatchlist}
          subtitle={`/ ${totalWatchlist} apps`}
          icon={BookmarkCheck}
          iconColor="text-indigo-400"
          iconBg="bg-indigo-500/10 border-indigo-500/20"
          to="/watchlist"
          linkText="Manage Watchlist"
        />

        {/* Active Feeds */}
        <StatCard
          title="Active Feeds"
          value={activeFeeds}
          subtitle={`/ ${totalFeeds} sources`}
          icon={Rss}
          iconColor="text-sky-400"
          iconBg="bg-sky-500/10 border-sky-500/20"
          to="/feeds"
          linkText="Configure Feeds"
        />

        {/* Completed Downloads */}
        <StatCard
          title="Downloads Completed"
          value={completedDownloads}
          subtitle={<span className="text-emerald-400 font-medium">ingested</span>}
          icon={CheckCircle2}
          iconColor="text-emerald-400"
          iconBg="bg-emerald-500/10 border-emerald-500/20"
          to="/history"
          linkText="View History"
        />

        {/* System Status */}
        <StatCard
          title="System Status"
          value={
            <span className={isHealthy ? 'text-emerald-400 capitalize' : 'text-amber-400 capitalize'}>
              {health?.status || (isHealthLoading ? 'Checking...' : 'Offline')}
            </span>
          }
          subtitle={
            <span className="font-mono text-slate-400 text-xs">
              {health?.version ? `v${health.version}` : 'v0.1.0'}
            </span>
          }
          icon={Activity}
          iconColor={isHealthy ? 'text-emerald-400' : 'text-amber-400'}
          iconBg={
            isHealthy
              ? 'bg-emerald-500/10 border-emerald-500/20'
              : 'bg-amber-500/10 border-amber-500/20'
          }
          href="/docs"
          linkText="API Status"
        />
      </div>

      {/* Live Activity & Queue & Recent Ingests */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left: Active Tasks Queue (2 columns wide) */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Radio className="w-5 h-5 text-indigo-400 animate-pulse" />
              <span>Live Activity &amp; Queue</span>
            </h2>
            <Link
              to="/history"
              className="text-xs font-medium text-indigo-400 hover:text-indigo-300 flex items-center gap-1 group transition"
            >
              <span>View All</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          </div>

          <div className="glass-panel rounded-2xl border border-slate-800 overflow-hidden shadow-xl">
            {queue.length === 0 ? (
              <div className="p-12 text-center text-slate-500">
                <Clock className="w-12 h-12 mx-auto mb-3 text-slate-600 opacity-60" />
                <p className="text-sm font-medium text-slate-300">No active tasks in queue</p>
                <p className="text-xs text-slate-500 mt-1">
                  Pending or resolving APK downloads will appear here in real-time.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-slate-800/80">
                {queue.map((task) => (
                  <div
                    key={task.id}
                    className="p-4 flex items-center justify-between gap-4 hover:bg-slate-900/50 transition"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="p-2.5 rounded-xl bg-slate-800/80 text-slate-300 border border-slate-700/60 shrink-0">
                        <FileCode2 className="w-5 h-5 text-indigo-400" />
                      </div>
                      <div className="min-w-0">
                        <h4 className="text-sm font-semibold text-slate-100 truncate">
                          {task.feed_item_title}
                        </h4>
                        <div className="flex items-center gap-2 text-xs text-slate-400 mt-0.5 flex-wrap">
                          <span className="font-mono text-slate-300">
                            v{task.matched_version || 'unknown'}
                          </span>
                          <span>•</span>
                          <span className="text-indigo-400 font-medium">
                            {task.matched_releaser || 'Unknown Releaser'}
                          </span>
                          {task.download_tier && (
                            <>
                              <span>•</span>
                              <Badge tier={task.download_tier} size="xs" />
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      <Badge status={task.status} size="sm" />

                      {task.status === 'failed' && (
                        <button
                          type="button"
                          onClick={() => handleRetryTask(task.id)}
                          disabled={retryingTaskId === task.id}
                          className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-rose-500/15 text-rose-300 hover:bg-rose-500/25 border border-rose-500/30 transition flex items-center gap-1.5 disabled:opacity-50"
                        >
                          <RotateCw
                            className={`w-3.5 h-3.5 ${
                              retryingTaskId === task.id ? 'animate-spin' : ''
                            }`}
                          />
                          <span>Retry</span>
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: Recent Ingests (1 column wide) */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              <span>Recent Ingests</span>
            </h2>
            <Link
              to="/history"
              className="text-xs font-medium text-slate-400 hover:text-slate-200 transition"
            >
              History &rarr;
            </Link>
          </div>

          <div className="glass-panel rounded-2xl border border-slate-800 overflow-hidden shadow-xl divide-y divide-slate-800/80">
            {recentIngests.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-sm">
                No completed history recorded yet.
              </div>
            ) : (
              recentIngests.map((item) => (
                <div key={item.id} className="p-4 hover:bg-slate-900/40 transition">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-slate-200 truncate">
                      {item.app_name}
                    </span>
                    <span className="text-xs font-mono font-medium text-emerald-400 shrink-0">
                      {formatBytes(item.file_size)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs text-slate-400 mt-1">
                    <span className="truncate mr-2">
                      v{item.version || '-'} • {item.releaser || '-'}
                    </span>
                    <span className="shrink-0 text-slate-500 font-mono text-[11px]">
                      {formatDate(item.downloaded_at)}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Manual Download Modal */}
      <ManualDownloadModal />
    </div>
  );
};

export default Dashboard;
