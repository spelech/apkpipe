import React, { useEffect, useState } from 'react';
import { Bookmark, Loader2, Save, Plus } from 'lucide-react';
import { Modal } from '../common/Modal';
import {
  useCreateWatchlistMutation,
  useUpdateWatchlistMutation,
} from '../../api/useWatchlist';
import { useToastStore } from '../../stores';
import type { WatchlistItem, WatchlistItemCreate, WatchlistItemUpdate } from '../../api/types';

export interface WatchlistModalProps {
  isOpen: boolean;
  onClose: () => void;
  item?: WatchlistItem | null;
  onSuccess?: (item: WatchlistItem) => void;
}

interface FormState {
  app_name: string;
  package_name: string;
  category: string;
  min_version: string;
  title_regex: string;
  releaser_whitelist_raw: string;
  releaser_blacklist_raw: string;
  enabled: boolean;
}

const defaultFormState: FormState = {
  app_name: '',
  package_name: '',
  category: 'Apps',
  min_version: '0.0.0',
  title_regex: '',
  releaser_whitelist_raw: '',
  releaser_blacklist_raw: '',
  enabled: true,
};

export const WatchlistModal: React.FC<WatchlistModalProps> = ({
  isOpen,
  onClose,
  item,
  onSuccess,
}) => {
  const [form, setForm] = useState<FormState>(defaultFormState);
  const isEditMode = !!item;

  const createMutation = useCreateWatchlistMutation();
  const updateMutation = useUpdateWatchlistMutation();
  const isPending = createMutation.isPending || updateMutation.isPending;

  const addToast = useToastStore((state) => state.addToast);

  useEffect(() => {
    if (isOpen) {
      if (item) {
        setForm({
          app_name: item.app_name || '',
          package_name: item.package_name || '',
          category: item.category || 'Apps',
          min_version: item.min_version || '0.0.0',
          title_regex: item.title_regex || '',
          releaser_whitelist_raw: (item.releaser_whitelist || []).join(', '),
          releaser_blacklist_raw: (item.releaser_blacklist || []).join(', '),
          enabled: item.enabled ?? true,
        });
      } else {
        setForm(defaultFormState);
      }
    }
  }, [isOpen, item]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value, type } = e.target;
    if (type === 'checkbox') {
      const checked = (e.target as HTMLInputElement).checked;
      setForm((prev) => ({ ...prev, [name]: checked }));
    } else {
      setForm((prev) => ({ ...prev, [name]: value }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const trimmedName = form.app_name.trim();
    if (!trimmedName) {
      addToast({
        type: 'warning',
        title: 'Validation Error',
        message: 'Application name is required',
      });
      return;
    }

    const whitelist = form.releaser_whitelist_raw
      ? form.releaser_whitelist_raw
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
      : [];

    const blacklist = form.releaser_blacklist_raw
      ? form.releaser_blacklist_raw
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
      : [];

    try {
      if (isEditMode && item) {
        const payload: WatchlistItemUpdate = {
          app_name: trimmedName,
          package_name: form.package_name.trim() || null,
          category: form.category.trim() || 'Apps',
          min_version: form.min_version.trim() || '0.0.0',
          title_regex: form.title_regex.trim() || null,
          releaser_whitelist: whitelist,
          releaser_blacklist: blacklist,
          enabled: form.enabled,
        };

        const updated = await updateMutation.mutateAsync({ id: item.id, data: payload });
        addToast({
          type: 'success',
          title: 'Watchlist Updated',
          message: `Successfully updated '${updated.app_name}'`,
        });
        onSuccess?.(updated);
      } else {
        const payload: WatchlistItemCreate = {
          app_name: trimmedName,
          package_name: form.package_name.trim() || null,
          category: form.category.trim() || 'Apps',
          min_version: form.min_version.trim() || '0.0.0',
          title_regex: form.title_regex.trim() || null,
          releaser_whitelist: whitelist,
          releaser_blacklist: blacklist,
          enabled: form.enabled,
        };

        const created = await createMutation.mutateAsync(payload);
        addToast({
          type: 'success',
          title: 'Watchlist Created',
          message: `Added '${created.app_name}' to monitored watchlist`,
        });
        onSuccess?.(created);
      }

      onClose();
    } catch (err: any) {
      const message = err?.message || 'Failed to save watchlist item';
      addToast({
        type: 'error',
        title: isEditMode ? 'Update Failed' : 'Creation Failed',
        message,
      });
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={isPending ? () => {} : onClose}
      title={
        <div className="flex items-center gap-2">
          <Bookmark className="w-5 h-5 text-indigo-400" />
          <span>{isEditMode ? 'Edit Monitored Application' : 'Add Application to Watchlist'}</span>
        </div>
      }
      description={
        isEditMode
          ? 'Modify matching regex, version threshold, or releaser constraints.'
          : 'Define title matching rules, releaser filters, and auto-download requirements.'
      }
      maxWidth="lg"
      showCloseButton={!isPending}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              App Name <span className="text-rose-400">*</span>
            </label>
            <input
              type="text"
              name="app_name"
              value={form.app_name}
              onChange={handleChange}
              required
              placeholder="e.g. Spotify"
              className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Package Name (Optional)
            </label>
            <input
              type="text"
              name="package_name"
              value={form.package_name}
              onChange={handleChange}
              placeholder="com.spotify.music"
              className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Category
            </label>
            <input
              type="text"
              name="category"
              value={form.category}
              onChange={handleChange}
              placeholder="Apps / Games / Media"
              className="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Min Version
            </label>
            <input
              type="text"
              name="min_version"
              value={form.min_version}
              onChange={handleChange}
              placeholder="0.0.0"
              className="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
            Title Regex Pattern (Optional)
          </label>
          <input
            type="text"
            name="title_regex"
            value={form.title_regex}
            onChange={handleChange}
            placeholder="^Spotify.*\[Premium\].*"
            className="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-700/80 text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
            Releaser Whitelist (Comma-separated)
          </label>
          <input
            type="text"
            name="releaser_whitelist_raw"
            value={form.releaser_whitelist_raw}
            onChange={handleChange}
            placeholder="Balatan, derrin, mods_king"
            className="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
          />
          <p className="text-[11px] text-slate-500 mt-1">
            Only download releases tagged with these releasers. Leave empty to allow any releaser.
          </p>
        </div>

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
            Releaser Blacklist (Comma-separated)
          </label>
          <input
            type="text"
            name="releaser_blacklist_raw"
            value={form.releaser_blacklist_raw}
            onChange={handleChange}
            placeholder="spammer, untrusted_uploader"
            className="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
          />
          <p className="text-[11px] text-slate-500 mt-1">
            Reject releases posted by these specific releasers or accounts.
          </p>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <input
            type="checkbox"
            id="watchlist_enabled_check"
            name="enabled"
            checked={form.enabled}
            onChange={handleChange}
            className="w-4 h-4 rounded bg-slate-950 border-slate-700 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-slate-900 cursor-pointer"
          />
          <label
            htmlFor="watchlist_enabled_check"
            className="text-sm font-medium text-slate-300 cursor-pointer select-none"
          >
            Enable monitoring immediately for this application
          </label>
        </div>

        <div className="pt-4 flex items-center justify-end gap-3 border-t border-slate-800/80">
          <button
            type="button"
            onClick={onClose}
            disabled={isPending}
            className="px-4 py-2 rounded-xl text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 transition disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isPending}
            className="px-5 py-2 rounded-xl text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/25 transition flex items-center gap-2 disabled:opacity-50"
          >
            {isPending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Saving...</span>
              </>
            ) : isEditMode ? (
              <>
                <Save className="w-4 h-4" />
                <span>Update Application</span>
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" />
                <span>Save Application</span>
              </>
            )}
          </button>
        </div>
      </form>
    </Modal>
  );
};

export default WatchlistModal;
