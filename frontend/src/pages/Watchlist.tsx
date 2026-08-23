import React, { useMemo, useState } from 'react';
import {
  Plus,
  Search,
  Edit2,
  Trash2,
  Loader2,
  Package,
} from 'lucide-react';
import {
  useWatchlistQuery,
  useToggleWatchlistMutation,
  useDeleteWatchlistMutation,
} from '../api';
import { useToastStore } from '../stores';
import { ConfirmDialog } from '../components/common';
import { WatchlistModal } from '../components/modals';
import type { WatchlistItem } from '../api/types';


export const Watchlist: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'enabled' | 'disabled'>('all');

  // Modal states
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<WatchlistItem | null>(null);

  // Deletion state
  const [itemToDelete, setItemToDelete] = useState<WatchlistItem | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Toggling state per-id to prevent double clicks
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const addToast = useToastStore((state) => state.addToast);

  // Queries & Mutations
  const { data: items = [], isLoading } = useWatchlistQuery();
  const toggleMutation = useToggleWatchlistMutation();
  const deleteMutation = useDeleteWatchlistMutation();

  // Unique categories derived from items
  const categories = useMemo(() => {
    const set = new Set<string>();
    items.forEach((item) => {
      if (item.category) set.add(item.category);
    });
    return Array.from(set).sort();
  }, [items]);

  // Filtered items list
  const filteredItems = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    return items.filter((item) => {
      const matchesSearch =
        !q ||
        item.app_name.toLowerCase().includes(q) ||
        (item.package_name && item.package_name.toLowerCase().includes(q)) ||
        (item.title_regex && item.title_regex.toLowerCase().includes(q));

      const matchesCat = !categoryFilter || item.category === categoryFilter;

      const matchesStatus =
        statusFilter === 'all' ||
        (statusFilter === 'enabled' && item.enabled) ||
        (statusFilter === 'disabled' && !item.enabled);

      return matchesSearch && matchesCat && matchesStatus;
    });
  }, [items, searchQuery, categoryFilter, statusFilter]);

  const handleOpenAdd = () => {
    setEditingItem(null);
    setModalOpen(true);
  };

  const handleOpenEdit = (item: WatchlistItem) => {
    setEditingItem(item);
    setModalOpen(true);
  };

  const handleToggleEnabled = async (item: WatchlistItem) => {
    const nextStatus = !item.enabled;
    setTogglingId(item.id);
    try {
      await toggleMutation.mutateAsync({ id: item.id, enabled: nextStatus });
      addToast({
        type: 'info',
        title: 'Status Updated',
        message: `'${item.app_name}' is now ${nextStatus ? 'enabled' : 'disabled'}`,
        duration: 3000,
      });
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Update Failed',
        message: err?.message || 'Failed to update item status',
      });
    } finally {
      setTogglingId(null);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!itemToDelete) return;
    setIsDeleting(true);
    try {
      await deleteMutation.mutateAsync(itemToDelete.id);
      addToast({
        type: 'success',
        title: 'Application Removed',
        message: `Successfully removed '${itemToDelete.app_name}' from watchlist`,
      });
      setItemToDelete(null);
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Deletion Failed',
        message: err?.message || 'Failed to delete application',
      });
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              Monitored Applications
            </h1>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-mono">
              {items.length} Total
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Configure automated matching rules, releaser filters, and minimum version constraints.
          </p>
        </div>

        <button
          type="button"
          onClick={handleOpenAdd}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/25 transition transform active:scale-95 shrink-0 self-start sm:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span>Add Application</span>
        </button>
      </div>

      {/* Search & Filters */}
      <div className="glass-panel p-4 rounded-2xl border border-slate-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Search Input */}
        <div className="relative flex-1">
          <Search className="w-5 h-5 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter by app name, package, or regex pattern..."
            className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-900 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
          />
        </div>

        {/* Dropdowns */}
        <div className="flex items-center gap-3 flex-wrap sm:flex-nowrap">
          <div className="relative flex-1 sm:flex-initial">
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="w-full sm:w-auto px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700/80 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            >
              <option value="">All Categories</option>
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>

          <div className="relative flex-1 sm:flex-initial">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as 'all' | 'enabled' | 'disabled')}
              className="w-full sm:w-auto px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700/80 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            >
              <option value="all">All Statuses</option>
              <option value="enabled">Enabled Only</option>
              <option value="disabled">Disabled Only</option>
            </select>
          </div>

          {(searchQuery || categoryFilter || statusFilter !== 'all') && (
            <button
              type="button"
              onClick={() => {
                setSearchQuery('');
                setCategoryFilter('');
                setStatusFilter('all');
              }}
              className="px-3 py-2 text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 rounded-xl transition"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Watchlist Table */}
      <div className="glass-panel rounded-2xl border border-slate-800 overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-900/90 text-xs uppercase font-semibold text-slate-400 border-b border-slate-800 tracking-wider">
              <tr>
                <th className="px-6 py-4">Application</th>
                <th className="px-6 py-4">Package Name</th>
                <th className="px-6 py-4">Min Version</th>
                <th className="px-6 py-4">Releasers</th>
                <th className="px-6 py-4 text-center">Status</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-16 text-center text-slate-500">
                    <div className="inline-flex items-center gap-2 text-sm text-indigo-400">
                      <Loader2 className="w-5 h-5 animate-spin" />
                      <span>Loading watchlist apps...</span>
                    </div>
                  </td>
                </tr>
              ) : filteredItems.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-16 text-center text-slate-500">
                    <div className="max-w-xs mx-auto space-y-2">
                      <Package className="w-10 h-10 mx-auto text-slate-600 opacity-60" />
                      <p className="text-sm font-medium text-slate-300">
                        {items.length === 0
                          ? 'No applications in watchlist'
                          : 'No matching applications found'}
                      </p>
                      <p className="text-xs text-slate-500">
                        {items.length === 0
                          ? 'Click "Add Application" to create your first automated monitoring rule.'
                          : 'Try adjusting your search query or filters.'}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredItems.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-900/40 transition">
                    {/* Application Details */}
                    <td className="px-6 py-4">
                      <div className="font-bold text-white text-base tracking-tight">
                        {item.app_name}
                      </div>
                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        {item.category && (
                          <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-800/90 text-slate-300 border border-slate-700/60">
                            {item.category}
                          </span>
                        )}
                        {item.title_regex && (
                          <span
                            className="px-2 py-0.5 rounded-md text-[11px] font-mono bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 max-w-xs truncate"
                            title={`Regex: ${item.title_regex}`}
                          >
                            Regex: {item.title_regex}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Package Name */}
                    <td className="px-6 py-4 font-mono text-xs text-slate-400">
                      {item.package_name ? (
                        <span className="text-slate-300">{item.package_name}</span>
                      ) : (
                        <span className="text-slate-600">-</span>
                      )}
                    </td>

                    {/* Min Version */}
                    <td className="px-6 py-4">
                      <span className="px-2.5 py-1 rounded-lg text-xs font-mono font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                        ≥ {item.min_version || '0.0.0'}
                      </span>
                    </td>

                    {/* Releasers */}
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap gap-1.5 max-w-xs">
                        {(!item.releaser_whitelist || item.releaser_whitelist.length === 0) &&
                        (!item.releaser_blacklist || item.releaser_blacklist.length === 0) ? (
                          <span className="text-xs text-slate-500 italic">Any releaser</span>
                        ) : null}

                        {item.releaser_whitelist?.map((rel) => (
                          <span
                            key={`wl-${rel}`}
                            className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/20"
                          >
                            + {rel}
                          </span>
                        ))}

                        {item.releaser_blacklist?.map((rel) => (
                          <span
                            key={`bl-${rel}`}
                            className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-rose-500/10 text-rose-300 border border-rose-500/20"
                          >
                            - {rel}
                          </span>
                        ))}
                      </div>
                    </td>

                    {/* Status Toggle */}
                    <td className="px-6 py-4 text-center">
                      <button
                        type="button"
                        onClick={() => handleToggleEnabled(item)}
                        disabled={togglingId === item.id}
                        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-50 ${
                          item.enabled ? 'bg-emerald-600' : 'bg-slate-700'
                        }`}
                        aria-label={`Toggle monitoring for ${item.app_name}`}
                      >
                        <span
                          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                            item.enabled ? 'translate-x-5' : 'translate-x-0'
                          }`}
                        />
                      </button>
                    </td>

                    {/* Actions */}
                    <td className="px-6 py-4 text-right space-x-2 shrink-0">
                      <button
                        type="button"
                        onClick={() => handleOpenEdit(item)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700/80 transition"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                        <span>Edit</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setItemToDelete(item)}
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

      {/* Add / Edit Watchlist Modal */}
      <WatchlistModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        item={editingItem}
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={!!itemToDelete}
        onClose={() => setItemToDelete(null)}
        onConfirm={handleDeleteConfirm}
        title="Delete Monitored Application?"
        message={
          <span>
            Are you sure you want to remove{' '}
            <strong className="text-white font-semibold">{itemToDelete?.app_name}</strong> from the
            monitored watchlist? Automated release matching for this app will cease.
          </span>
        }
        confirmText="Delete Application"
        variant="danger"
        isLoading={isDeleting}
      />
    </div>
  );
};

export default Watchlist;

