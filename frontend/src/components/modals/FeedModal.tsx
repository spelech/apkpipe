import React, { useEffect, useState } from 'react';
import { Rss, Loader2, Save, Plus } from 'lucide-react';
import { Modal } from '../common/Modal';
import { useCreateFeedMutation, useUpdateFeedMutation } from '../../api/useFeeds';
import { useToastStore } from '../../stores';
import type { FeedSource, FeedSourceCreate, FeedSourceUpdate } from '../../api/types';

export interface FeedModalProps {
  isOpen: boolean;
  onClose: () => void;
  item?: FeedSource | null;
  onSuccess?: (item: FeedSource) => void;
}

interface FormState {
  name: string;
  url: string;
  feed_type: string;
  poll_interval_minutes: number;
  enabled: boolean;
}

const defaultFormState: FormState = {
  name: '',
  url: '',
  feed_type: 'mobilism_rss',
  poll_interval_minutes: 30,
  enabled: true,
};

export const FeedModal: React.FC<FeedModalProps> = ({
  isOpen,
  onClose,
  item,
  onSuccess,
}) => {
  const [form, setForm] = useState<FormState>(defaultFormState);
  const isEditMode = !!item;

  const createMutation = useCreateFeedMutation();
  const updateMutation = useUpdateFeedMutation();
  const isPending = createMutation.isPending || updateMutation.isPending;

  const addToast = useToastStore((state) => state.addToast);

  useEffect(() => {
    if (isOpen) {
      if (item) {
        setForm({
          name: item.name || '',
          url: item.url || '',
          feed_type: item.feed_type || 'mobilism_rss',
          poll_interval_minutes: item.poll_interval_minutes || 30,
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
    } else if (type === 'number') {
      setForm((prev) => ({ ...prev, [name]: parseInt(value, 10) || 0 }));
    } else {
      setForm((prev) => ({ ...prev, [name]: value }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const trimmedName = form.name.trim();
    const trimmedUrl = form.url.trim();

    if (!trimmedName) {
      addToast({
        type: 'warning',
        title: 'Validation Error',
        message: 'Feed source name is required',
      });
      return;
    }

    if (!trimmedUrl) {
      addToast({
        type: 'warning',
        title: 'Validation Error',
        message: 'Feed endpoint URL is required',
      });
      return;
    }

    const pollMinutes = Math.max(1, form.poll_interval_minutes || 30);

    try {
      if (isEditMode && item) {
        const payload: FeedSourceUpdate = {
          name: trimmedName,
          url: trimmedUrl,
          feed_type: form.feed_type,
          poll_interval_minutes: pollMinutes,
          enabled: form.enabled,
        };

        const updated = await updateMutation.mutateAsync({ id: item.id, data: payload });
        addToast({
          type: 'success',
          title: 'Feed Updated',
          message: `Successfully updated '${updated.name}'`,
        });
        onSuccess?.(updated);
      } else {
        const payload: FeedSourceCreate = {
          name: trimmedName,
          url: trimmedUrl,
          feed_type: form.feed_type,
          poll_interval_minutes: pollMinutes,
          enabled: form.enabled,
        };

        const created = await createMutation.mutateAsync(payload);
        addToast({
          type: 'success',
          title: 'Feed Created',
          message: `Added '${created.name}' to monitored feeds`,
        });
        onSuccess?.(created);
      }

      onClose();
    } catch (err: any) {
      const message = err?.message || 'Failed to save feed source';
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
          <Rss className="w-5 h-5 text-sky-400" />
          <span>{isEditMode ? 'Edit Feed Configuration' : 'Add Feed Source'}</span>
        </div>
      }
      description={
        isEditMode
          ? 'Modify feed endpoint, polling interval, parser type, or status.'
          : 'Configure a new RSS or forum release feed for continuous polling and extraction.'
      }
      maxWidth="lg"
      showCloseButton={!isPending}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
            Feed Name <span className="text-rose-400">*</span>
          </label>
          <input
            type="text"
            name="name"
            value={form.name}
            onChange={handleChange}
            required
            placeholder="e.g. Mobilism Main Apps RSS"
            className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
            Feed URL / Endpoint <span className="text-rose-400">*</span>
          </label>
          <input
            type="url"
            name="url"
            value={form.url}
            onChange={handleChange}
            required
            placeholder="https://forum.mobilism.org/feed.php?f=398"
            className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Feed Type
            </label>
            <select
              name="feed_type"
              value={form.feed_type}
              onChange={handleChange}
              className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition"
            >
              <option value="mobilism_rss">mobilism_rss (Mobilism Topic Feed)</option>
              <option value="generic_rss">generic_rss (Standard RSS 2.0)</option>
              <option value="atom">atom (Atom Feed)</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Poll Frequency (Minutes)
            </label>
            <input
              type="number"
              name="poll_interval_minutes"
              value={form.poll_interval_minutes}
              onChange={handleChange}
              min={1}
              max={1440}
              placeholder="30"
              className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition"
            />
          </div>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <input
            type="checkbox"
            id="feed_modal_enabled_check"
            name="enabled"
            checked={form.enabled}
            onChange={handleChange}
            className="w-4 h-4 rounded bg-slate-950 border-slate-700 text-sky-600 focus:ring-sky-500 focus:ring-offset-slate-900 cursor-pointer"
          />
          <label
            htmlFor="feed_modal_enabled_check"
            className="text-sm font-medium text-slate-300 cursor-pointer select-none"
          >
            Enable automatic background polling for this source
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
            className="px-5 py-2 rounded-xl text-sm font-semibold bg-sky-600 hover:bg-sky-500 text-white shadow-lg shadow-sky-600/25 transition flex items-center gap-2 disabled:opacity-50"
          >
            {isPending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Saving...</span>
              </>
            ) : isEditMode ? (
              <>
                <Save className="w-4 h-4" />
                <span>Update Feed</span>
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" />
                <span>Save Feed</span>
              </>
            )}
          </button>
        </div>
      </form>
    </Modal>
  );
};

export default FeedModal;
