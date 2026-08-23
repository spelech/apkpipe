import React, { useMemo, useState } from 'react';
import {
  History as HistoryIcon,
  Radio,
  Search,
  RotateCw,
  XCircle,
  AlertCircle,
  Clock,
  Loader2,
  RefreshCw,
  CheckCircle2,
} from 'lucide-react';
import {
  useQueueQuery,
  useHistoryQuery,
  useRetryDownloadMutation,
  useCancelDownloadMutation,
} from '../api';
import { useUIStore, useToastStore } from '../stores';
import { Badge, ConfirmDialog } from '../components/common';
import { formatBytes, formatDate, formatDuration } from '../utils';
import type { DownloadTask } from '../api/types';



export const History: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'queue' | 'history'>('queue');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // Auto refresh state from Zustand UI store
  const autoRefreshQueue = useUIStore((state) => state.autoRefreshQueue);
  const setAutoRefreshQueue = useUIStore((state) => state.setAutoRefreshQueue);
  const queuePollingInterval = useUIStore((state) => state.queuePollingInterval);

  // Per-task action loading states
  const [retryingId, setRetryingId] = useState<number | null>(null);
  const [taskToCancel, setTaskToCancel] = useState<DownloadTask | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);

  const addToast = useToastStore((state) => state.addToast);

  // Queries
  const {
    data: queue = [],
    isLoading: isQueueLoading,
    isFetching: isQueueFetching,
    refetch: refetchQueue,
  } = useQueueQuery(autoRefreshQueue ? queuePollingInterval : undefined);

  const {
    data: history = [],
    isLoading: isHistoryLoading,
    isFetching: isHistoryFetching,
    refetch: refetchHistory,
  } = useHistoryQuery();

  const retryMutation = useRetryDownloadMutation();
  const cancelMutation = useCancelDownloadMutation();

  const isRefreshing = isQueueFetching || isHistoryFetching;

  // Filtered active queue items
  const filteredQueue = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    return queue.filter((task) => {
      const matchesSearch =
        !q ||
        task.feed_item_title.toLowerCase().includes(q) ||
        (task.matched_version && task.matched_version.toLowerCase().includes(q)) ||
        (task.matched_releaser && task.matched_releaser.toLowerCase().includes(q)) ||
        (task.error_message && task.error_message.toLowerCase().includes(q));

      const matchesStatus = !statusFilter || task.status === statusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [queue, searchQuery, statusFilter]);

  // Filtered completed history items
  const filteredHistory = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    return history.filter((item) => {
      const matchesSearch =
        !q ||
        item.app_name.toLowerCase().includes(q) ||
        (item.version && item.version.toLowerCase().includes(q)) ||
        (item.releaser && item.releaser.toLowerCase().includes(q)) ||
        (item.target_path && item.target_path.toLowerCase().includes(q));

      const matchesStatus = !statusFilter || item.status === statusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [history, searchQuery, statusFilter]);

  const handleManualRefresh = async () => {
    try {
      await Promise.all([refetchQueue(), refetchHistory()]);
      addToast({
        type: 'info',
        title: 'Refreshed',
        message: 'Updated queue and history records',
        duration: 2000,
      });
    } catch {
      addToast({
        type: 'error',
        title: 'Refresh Error',
        message: 'Failed to refresh download data',
      });
    }
  };

  const handleRetryTask = async (taskId: number) => {
    setRetryingId(taskId);
    try {
      await retryMutation.mutateAsync(taskId);
      addToast({
        type: 'success',
        title: 'Task Re-queued',
        message: `Task #${taskId} has been re-queued for processing`,
      });
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Retry Failed',
        message: err?.message || `Failed to retry task #${taskId}`,
      });
    } finally {
      setRetryingId(null);
    }
  };

  const handleCancelConfirm = async () => {
    if (!taskToCancel) return;
    setIsCancelling(true);
    try {
      await cancelMutation.mutateAsync(taskToCancel.id);
      addToast({
        type: 'success',
        title: 'Task Cancelled',
        message: `Cancelled task #${taskToCancel.id} (${taskToCancel.feed_item_title})`,
      });
      setTaskToCancel(null);
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Cancel Failed',
        message: err?.message || `Failed to cancel task #${taskToCancel.id}`,
      });
    } finally {
      setIsCancelling(false);
    }
  };

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              Download Queue &amp; History
            </h1>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-mono">
              {queue.length} Active
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Monitor real-time download pipelines, resolver tiers, extraction tasks, and ingestion logs.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0 flex-wrap sm:flex-nowrap">
          {/* Live Auto-Refresh Switch */}
          <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-300">
            <span
              className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                autoRefreshQueue ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'
              }`}
            />
            <span className="font-medium text-slate-400">Live Poll:</span>
            <button
              type="button"
              onClick={() => setAutoRefreshQueue(!autoRefreshQueue)}
              className={`font-semibold hover:underline transition ${
                autoRefreshQueue ? 'text-emerald-400' : 'text-slate-500'
              }`}
            >
              {autoRefreshQueue ? 'ON (5s)' : 'PAUSED'}
            </button>
          </div>

          {/* Manual Refresh Button */}
          <button
            type="button"
            onClick={handleManualRefresh}
            disabled={isRefreshing}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm font-semibold bg-slate-800/80 hover:bg-slate-700 text-slate-200 border border-slate-700/60 transition disabled:opacity-50"
            title="Refresh queue and history immediately"
          >
            <RefreshCw
              className={`w-4 h-4 text-slate-400 ${isRefreshing ? 'animate-spin' : ''}`}
            />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Tabs & Filters Bar */}
      <div className="glass-panel p-4 rounded-2xl border border-slate-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Dual Tab Switcher */}
        <div className="flex items-center gap-1.5 bg-slate-900/90 p-1 rounded-xl border border-slate-800">
          <button
            type="button"
            onClick={() => setActiveTab('queue')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition ${
              activeTab === 'queue'
                ? 'bg-indigo-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Radio className="w-4 h-4" />
            <span>Active Queue</span>
            <span
              className={`px-2 py-0.5 rounded-full text-xs font-mono font-medium ${
                activeTab === 'queue' ? 'bg-indigo-700 text-white' : 'bg-slate-800 text-slate-400'
              }`}
            >
              {queue.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('history')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition ${
              activeTab === 'history'
                ? 'bg-indigo-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <HistoryIcon className="w-4 h-4" />
            <span>Completed History</span>
            <span
              className={`px-2 py-0.5 rounded-full text-xs font-mono font-medium ${
                activeTab === 'history'
                  ? 'bg-indigo-700 text-white'
                  : 'bg-slate-800 text-slate-400'
              }`}
            >
              {history.length}
            </span>
          </button>
        </div>

        {/* Filter & Search Bar */}
        <div className="flex items-center gap-3 flex-wrap sm:flex-nowrap">
          <div className="relative flex-1 sm:w-64">
            <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search title, releaser, path..."
              className="w-full pl-9 pr-3.5 py-2 rounded-xl bg-slate-900 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>

          <div className="relative flex-1 sm:flex-initial">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full sm:w-auto px-3.5 py-2 rounded-xl bg-slate-900 border border-slate-700/80 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            >
              <option value="">All Statuses</option>
              <option value="pending">Pending</option>
              <option value="resolving">Resolving</option>
              <option value="downloading">Downloading</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          {(searchQuery || statusFilter) && (
            <button
              type="button"
              onClick={() => {
                setSearchQuery('');
                setStatusFilter('');
              }}
              className="px-3 py-2 text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 rounded-xl transition"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Active Queue Tab View */}
      {activeTab === 'queue' && (
        <div className="glass-panel rounded-2xl border border-slate-800 overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-300">
              <thead className="bg-slate-900/90 text-xs uppercase font-semibold text-slate-400 border-b border-slate-800 tracking-wider">
                <tr>
                  <th className="px-6 py-4">Task ID &amp; Release Title</th>
                  <th className="px-6 py-4">Version &amp; Releaser</th>
                  <th className="px-6 py-4">Resolver Tier</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4">File Size</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {isQueueLoading ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-16 text-center text-slate-500">
                      <div className="inline-flex items-center gap-2 text-sm text-indigo-400">
                        <Loader2 className="w-5 h-5 animate-spin" />
                        <span>Loading active queue...</span>
                      </div>
                    </td>
                  </tr>
                ) : filteredQueue.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-16 text-center text-slate-500">
                      <div className="max-w-xs mx-auto space-y-2">
                        <Clock className="w-10 h-10 mx-auto text-slate-600 opacity-60" />
                        <p className="text-sm font-medium text-slate-300">
                          {queue.length === 0
                            ? 'No active tasks in queue'
                            : 'No matching queue items found'}
                        </p>
                        <p className="text-xs text-slate-500">
                          {queue.length === 0
                            ? 'Trigger a manual download or wait for feeds to match releases.'
                            : 'Try adjusting your search query or status filter.'}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  filteredQueue.map((task) => (
                    <tr key={task.id} className="hover:bg-slate-900/40 transition">
                      {/* Task ID & Release Title */}
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono text-slate-500 font-semibold">
                            #{task.id}
                          </span>
                          <span className="font-bold text-white text-sm">
                            {task.feed_item_title}
                          </span>
                        </div>
                        {task.error_message && (
                          <div
                            className="mt-1.5 text-xs text-rose-400 flex items-center gap-1.5 bg-rose-500/10 px-2 py-1 rounded-lg border border-rose-500/20 max-w-lg"
                            title={task.error_message}
                          >
                            <AlertCircle className="w-3.5 h-3.5 shrink-0 text-rose-400" />
                            <span className="truncate">{task.error_message}</span>
                          </div>
                        )}
                      </td>

                      {/* Version & Releaser */}
                      <td className="px-6 py-4">
                        <div className="text-xs text-slate-200 font-semibold font-mono">
                          v{task.matched_version || 'unknown'}
                        </div>
                        <div className="text-xs text-indigo-400 font-medium mt-0.5">
                          {task.matched_releaser || '-'}
                        </div>
                      </td>

                      {/* Resolver Tier */}
                      <td className="px-6 py-4">
                        {task.download_tier ? (
                          <Badge tier={task.download_tier} size="sm" />
                        ) : (
                          <span className="text-xs text-slate-500 font-mono">Auto / Pending</span>
                        )}
                      </td>

                      {/* Status */}
                      <td className="px-6 py-4">
                        <Badge status={task.status} size="sm" />
                      </td>

                      {/* File Size */}
                      <td className="px-6 py-4 font-mono text-xs text-slate-300">
                        {formatBytes(task.file_size)}
                      </td>

                      {/* Actions */}
                      <td className="px-6 py-4 text-right space-x-2 shrink-0">
                        {(task.status === 'failed' || task.status === 'pending') && (
                          <button
                            type="button"
                            onClick={() => handleRetryTask(task.id)}
                            disabled={retryingId === task.id}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 border border-indigo-500/20 transition disabled:opacity-50"
                          >
                            <RotateCw
                              className={`w-3.5 h-3.5 ${
                                retryingId === task.id ? 'animate-spin' : ''
                              }`}
                            />
                            <span>Retry</span>
                          </button>
                        )}

                        <button
                          type="button"
                          onClick={() => setTaskToCancel(task)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/20 transition"
                        >
                          <XCircle className="w-3.5 h-3.5" />
                          <span>Cancel</span>
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Completed History Tab View */}
      {activeTab === 'history' && (
        <div className="glass-panel rounded-2xl border border-slate-800 overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-300">
              <thead className="bg-slate-900/90 text-xs uppercase font-semibold text-slate-400 border-b border-slate-800 tracking-wider">
                <tr>
                  <th className="px-6 py-4">App &amp; Version</th>
                  <th className="px-6 py-4">Releaser</th>
                  <th className="px-6 py-4">Staged Target Path</th>
                  <th className="px-6 py-4">File Size</th>
                  <th className="px-6 py-4">Duration</th>
                  <th className="px-6 py-4">Tier</th>
                  <th className="px-6 py-4">Completed At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {isHistoryLoading ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-16 text-center text-slate-500">
                      <div className="inline-flex items-center gap-2 text-sm text-indigo-400">
                        <Loader2 className="w-5 h-5 animate-spin" />
                        <span>Loading audit history...</span>
                      </div>
                    </td>
                  </tr>
                ) : filteredHistory.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-16 text-center text-slate-500">
                      <div className="max-w-xs mx-auto space-y-2">
                        <CheckCircle2 className="w-10 h-10 mx-auto text-slate-600 opacity-60" />
                        <p className="text-sm font-medium text-slate-300">
                          {history.length === 0
                            ? 'No completed download records found'
                            : 'No matching history records found'}
                        </p>
                        <p className="text-xs text-slate-500">
                          Completed downloads will be recorded here with extraction and file size audit data.
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  filteredHistory.map((item) => (
                    <tr key={item.id} className="hover:bg-slate-900/40 transition">
                      {/* App & Version */}
                      <td className="px-6 py-4">
                        <div className="font-bold text-white text-sm">{item.app_name}</div>
                        <div className="text-xs text-slate-400 font-mono mt-0.5">
                          v{item.version || '-'}
                        </div>
                      </td>

                      {/* Releaser */}
                      <td className="px-6 py-4 font-mono text-xs text-indigo-400">
                        {item.releaser || '-'}
                      </td>

                      {/* Staged Target Path */}
                      <td
                        className="px-6 py-4 font-mono text-xs text-slate-400 max-w-xs truncate"
                        title={item.target_path || undefined}
                      >
                        {item.target_path || '-'}
                      </td>

                      {/* File Size */}
                      <td className="px-6 py-4 font-mono text-xs text-emerald-400 font-semibold">
                        {formatBytes(item.file_size)}
                      </td>

                      {/* Duration */}
                      <td className="px-6 py-4 text-xs text-slate-400 font-mono">
                        {formatDuration(item.duration_seconds)}
                      </td>

                      {/* Tier */}
                      <td className="px-6 py-4">
                        {item.download_tier ? (
                          <Badge tier={item.download_tier} size="sm" />
                        ) : (
                          <span className="text-xs text-slate-500 font-mono">-</span>
                        )}
                      </td>

                      {/* Completed At */}
                      <td className="px-6 py-4 font-mono text-xs text-slate-400">
                        {formatDate(item.downloaded_at)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Cancel Task Confirmation Dialog */}
      <ConfirmDialog
        isOpen={!!taskToCancel}
        onClose={() => setTaskToCancel(null)}
        onConfirm={handleCancelConfirm}
        title="Cancel Download Task?"
        message={
          <span>
            Are you sure you want to cancel task{' '}
            <strong className="text-white font-semibold">
              #{taskToCancel?.id} ({taskToCancel?.feed_item_title})
            </strong>
            ? Active downloads or resolution will be aborted.
          </span>
        }
        confirmText="Cancel Task"
        variant="danger"
        isLoading={isCancelling}
      />
    </div>
  );
};

export default History;

