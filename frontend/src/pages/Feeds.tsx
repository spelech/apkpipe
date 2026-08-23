import React, { useMemo, useState } from 'react';
import {
  Plus,
  Search,
  Edit2,
  Trash2,
  Loader2,
  Rss,
  RotateCw,
  ExternalLink,
  RefreshCw,
} from 'lucide-react';
import {
  useFeedsQuery,
  useToggleFeedMutation,
  useDeleteFeedMutation,
  usePollSingleFeedMutation,
  usePollAllFeedsMutation,
} from '../api';
import { useToastStore } from '../stores';
import { ConfirmDialog } from '../components/common';
import { FeedModal } from '../components/modals';
import { formatDate } from '../utils';
import type { FeedSource } from '../api/types';


export const Feeds: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'enabled' | 'disabled'>('all');

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<FeedSource | null>(null);

  // Deletion state
  const [itemToDelete, setItemToDelete] = useState<FeedSource | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Single polling & toggle tracker per id
  const [pollingId, setPollingId] = useState<number | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const addToast = useToastStore((state) => state.addToast);

  // Queries & Mutations
  const { data: feeds = [], isLoading } = useFeedsQuery();
  const toggleMutation = useToggleFeedMutation();

  const deleteMutation = useDeleteFeedMutation();
  const pollSingleMutation = usePollSingleFeedMutation();
  const pollAllMutation = usePollAllFeedsMutation();

  // Unique feed types
  const feedTypes = useMemo(() => {
    const set = new Set<string>();
    feeds.forEach((f) => {
      if (f.feed_type) set.add(f.feed_type);
    });
    return Array.from(set).sort();
  }, [feeds]);

  // Filtered feeds list
  const filteredFeeds = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    return feeds.filter((item) => {
      const matchesSearch =
        !q ||
        item.name.toLowerCase().includes(q) ||
        item.url.toLowerCase().includes(q) ||
        (item.feed_type && item.feed_type.toLowerCase().includes(q));

      const matchesType = !typeFilter || item.feed_type === typeFilter;

      const matchesStatus =
        statusFilter === 'all' ||
        (statusFilter === 'enabled' && item.enabled) ||
        (statusFilter === 'disabled' && !item.enabled);

      return matchesSearch && matchesType && matchesStatus;
    });
  }, [feeds, searchQuery, typeFilter, statusFilter]);

  const handleOpenAdd = () => {
    setEditingItem(null);
    setModalOpen(true);
  };

  const handleOpenEdit = (item: FeedSource) => {
    setEditingItem(item);
    setModalOpen(true);
  };

  const handleToggleEnabled = async (item: FeedSource) => {
    const nextStatus = !item.enabled;
    setTogglingId(item.id);
    try {
      await toggleMutation.mutateAsync({ id: item.id, enabled: nextStatus });
      addToast({
        type: 'info',
        title: 'Feed Status Updated',
        message: `'${item.name}' is now ${nextStatus ? 'enabled' : 'disabled'}`,
        duration: 3000,
      });
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Update Failed',
        message: err?.message || 'Failed to update feed status',
      });
    } finally {
      setTogglingId(null);
    }
  };

  const handlePollSingle = async (item: FeedSource) => {
    setPollingId(item.id);
    try {
      await pollSingleMutation.mutateAsync(item.id);
      addToast({
        type: 'success',
        title: 'Feed Polled',
        message: `Polled '${item.name}' successfully for new releases`,
      });
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Poll Failed',
        message: err?.message || `Failed to poll feed '${item.name}'`,
      });
    } finally {
      setPollingId(null);
    }
  };

  const handlePollAll = async () => {
    try {
      await pollAllMutation.mutateAsync();
      addToast({
        type: 'success',
        title: 'All Feeds Polled',
        message: `Triggered full refresh across all configured feeds`,
      });
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Poll All Failed',
        message: err?.message || 'Failed to poll feeds',
      });
    }
  };

  const handleDeleteConfirm = async () => {
    if (!itemToDelete) return;
    setIsDeleting(true);
    try {
      await deleteMutation.mutateAsync(itemToDelete.id);
      addToast({
        type: 'success',
        title: 'Feed Deleted',
        message: `Successfully removed '${itemToDelete.name}'`,
      });
      setItemToDelete(null);
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Deletion Failed',
        message: err?.message || 'Failed to delete feed source',
      });
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header & Primary Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              Feed Sources
            </h1>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/20 font-mono">
              {feeds.length} Configured
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Manage RSS and forum release feeds for continuous polling, matching, and extraction.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0 flex-wrap sm:flex-nowrap">
          <button
            type="button"
            onClick={handlePollAll}
            disabled={pollAllMutation.isPending || feeds.length === 0}
            className="inline-flex items-center gap-2 px-3.5 py-2.5 rounded-xl text-sm font-semibold bg-slate-800/80 hover:bg-slate-700 text-slate-200 border border-slate-700/60 transition disabled:opacity-50"
            title="Poll all configured feeds immediately"
          >
            <RefreshCw
              className={`w-4 h-4 text-sky-400 ${
                pollAllMutation.isPending ? 'animate-spin' : ''
              }`}
            />
            <span>{pollAllMutation.isPending ? 'Polling All...' : 'Poll All Feeds Now'}</span>
          </button>

          <button
            type="button"
            onClick={handleOpenAdd}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-sky-600 hover:bg-sky-500 text-white shadow-lg shadow-sky-600/25 transition transform active:scale-95 shrink-0"
          >
            <Plus className="w-4 h-4" />
            <span>Add Feed</span>
          </button>
        </div>
      </div>

      {/* Search & Filter Controls */}
      <div className="glass-panel p-4 rounded-2xl border border-slate-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        <div className="relative flex-1">
          <Search className="w-5 h-5 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search feeds by name, endpoint URL, or feed type..."
            className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-900 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition"
          />
        </div>

        <div className="flex items-center gap-3 flex-wrap sm:flex-nowrap">
          <div className="relative flex-1 sm:flex-initial">
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="w-full sm:w-auto px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700/80 text-sm text-slate-200 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition"
            >
              <option value="">All Types</option>
              {feedTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>

          <div className="relative flex-1 sm:flex-initial">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as 'all' | 'enabled' | 'disabled')}
              className="w-full sm:w-auto px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700/80 text-sm text-slate-200 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition"
            >
              <option value="all">All Statuses</option>
              <option value="enabled">Enabled Only</option>
              <option value="disabled">Disabled Only</option>
            </select>
          </div>

          {(searchQuery || typeFilter || statusFilter !== 'all') && (
            <button
              type="button"
              onClick={() => {
                setSearchQuery('');
                setTypeFilter('');
                setStatusFilter('all');
              }}
              className="px-3 py-2 text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 rounded-xl transition"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Feeds Table */}
      <div className="glass-panel rounded-2xl border border-slate-800 overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-900/90 text-xs uppercase font-semibold text-slate-400 border-b border-slate-800 tracking-wider">
              <tr>
                <th className="px-6 py-4">Feed Name &amp; Type</th>
                <th className="px-6 py-4">Endpoint URL</th>
                <th className="px-6 py-4">Poll Interval</th>
                <th className="px-6 py-4">Last Polled</th>
                <th className="px-6 py-4 text-center">Status</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-16 text-center text-slate-500">
                    <div className="inline-flex items-center gap-2 text-sm text-sky-400">
                      <Loader2 className="w-5 h-5 animate-spin" />
                      <span>Loading feed configurations...</span>
                    </div>
                  </td>
                </tr>
              ) : filteredFeeds.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-16 text-center text-slate-500">
                    <div className="max-w-xs mx-auto space-y-2">
                      <Rss className="w-10 h-10 mx-auto text-slate-600 opacity-60" />
                      <p className="text-sm font-medium text-slate-300">
                        {feeds.length === 0
                          ? 'No feed sources configured yet'
                          : 'No matching feeds found'}
                      </p>
                      <p className="text-xs text-slate-500">
                        {feeds.length === 0
                          ? 'Click "Add Feed" to register an RSS or Mobilism feed.'
                          : 'Try adjusting your search query or filters.'}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredFeeds.map((feed) => (
                  <tr key={feed.id} className="hover:bg-slate-900/40 transition">
                    {/* Feed Name & Type */}
                    <td className="px-6 py-4">
                      <div className="font-bold text-white text-base tracking-tight">
                        {feed.name}
                      </div>
                      <div className="mt-1">
                        <span className="px-2 py-0.5 rounded-md text-[11px] font-mono font-medium bg-slate-800 text-sky-300 border border-slate-700/80">
                          {feed.feed_type}
                        </span>
                      </div>
                    </td>

                    {/* Endpoint URL */}
                    <td className="px-6 py-4 font-mono text-xs text-slate-400 max-w-xs">
                      <a
                        href={feed.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 hover:text-sky-400 hover:underline truncate max-w-[260px]"
                        title={feed.url}
                      >
                        <span className="truncate">{feed.url}</span>
                        <ExternalLink className="w-3 h-3 shrink-0 opacity-60" />
                      </a>
                    </td>

                    {/* Poll Interval */}
                    <td className="px-6 py-4 text-xs font-semibold text-slate-300">
                      <span className="px-2.5 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 font-mono">
                        {feed.poll_interval_minutes} min
                      </span>
                    </td>

                    {/* Last Polled */}
                    <td className="px-6 py-4 text-xs text-slate-400 font-mono">
                      {formatDate(feed.last_polled_at)}
                    </td>

                    {/* Status Toggle */}
                    <td className="px-6 py-4 text-center">
                      <button
                        type="button"
                        onClick={() => handleToggleEnabled(feed)}
                        disabled={togglingId === feed.id}
                        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-50 ${
                          feed.enabled ? 'bg-emerald-600' : 'bg-slate-700'
                        }`}
                        aria-label={`Toggle feed ${feed.name}`}
                      >
                        <span
                          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                            feed.enabled ? 'translate-x-5' : 'translate-x-0'
                          }`}
                        />
                      </button>
                    </td>

                    {/* Actions */}
                    <td className="px-6 py-4 text-right space-x-2 shrink-0">
                      <button
                        type="button"
                        onClick={() => handlePollSingle(feed)}
                        disabled={pollingId === feed.id}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-sky-500/10 hover:bg-sky-500/20 text-sky-300 border border-sky-500/20 transition disabled:opacity-50"
                      >
                        <RotateCw
                          className={`w-3.5 h-3.5 ${
                            pollingId === feed.id ? 'animate-spin' : ''
                          }`}
                        />
                        <span>{pollingId === feed.id ? 'Polling...' : 'Poll Now'}</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => handleOpenEdit(feed)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700/80 transition"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                        <span>Edit</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => setItemToDelete(feed)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/20 transition"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span>Delete</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add / Edit Feed Modal */}
      <FeedModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        item={editingItem}
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={!!itemToDelete}
        onClose={() => setItemToDelete(null)}
        onConfirm={handleDeleteConfirm}
        title="Delete Feed Source?"
        message={
          <span>
            Are you sure you want to remove feed source{' '}
            <strong className="text-white font-semibold">{itemToDelete?.name}</strong>? Automated polling
            and indexing for this endpoint will stop.
          </span>
        }
        confirmText="Delete Feed"
        variant="danger"
        isLoading={isDeleting}
      />
    </div>
  );
};

export default Feeds;

