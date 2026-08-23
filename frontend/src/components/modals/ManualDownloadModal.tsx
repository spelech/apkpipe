import React, { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { Modal } from '../common/Modal';
import { useManualDownloadMutation } from '../../api/useDownloads';
import { useUIStore, useToastStore } from '../../stores';
import type { ManualDownloadRequest } from '../../api/types';

const initialFormData: ManualDownloadRequest = {
  url: '',
  app_name: '',
  version: '',
  releaser: '',
  category: 'Apps',
  download_tier: '',
  auto_resolve: true,
  trigger_ingest: true,
};

export const ManualDownloadModal: React.FC = () => {
  const manualModalOpen = useUIStore((state) => state.manualModalOpen);
  const setManualModalOpen = useUIStore((state) => state.setManualModalOpen);
  const addToast = useToastStore((state) => state.addToast);

  const [formData, setFormData] = useState<ManualDownloadRequest>(initialFormData);
  const manualDownloadMutation = useManualDownloadMutation();

  const handleClose = () => {
    if (manualDownloadMutation.isPending) return;
    setManualModalOpen(false);
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value, type } = e.target;
    if (type === 'checkbox') {
      const checked = (e.target as HTMLInputElement).checked;
      setFormData((prev) => ({ ...prev, [name]: checked }));
    } else {
      setFormData((prev) => ({ ...prev, [name]: value }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.url.trim()) {
      addToast({
        type: 'warning',
        title: 'Validation Error',
        message: 'Download or topic URL is required',
      });
      return;
    }

    const payload: ManualDownloadRequest = {
      url: formData.url.trim(),
      ...(formData.app_name?.trim() ? { app_name: formData.app_name.trim() } : {}),
      ...(formData.version?.trim() ? { version: formData.version.trim() } : {}),
      ...(formData.releaser?.trim() ? { releaser: formData.releaser.trim() } : {}),
      ...(formData.category?.trim() ? { category: formData.category.trim() } : {}),
      ...(formData.download_tier ? { download_tier: formData.download_tier } : {}),
      auto_resolve: formData.auto_resolve ?? true,
      trigger_ingest: formData.trigger_ingest ?? true,
    };

    try {
      const result = await manualDownloadMutation.mutateAsync(payload);
      addToast({
        type: 'success',
        title: 'Download Triggered',
        message: `Manual download queued for ${result.feed_item_title || payload.app_name || 'APK'}!`,
      });
      setFormData(initialFormData);
      setManualModalOpen(false);
    } catch (err: any) {
      const message = err?.message || 'Failed to trigger manual download';
      addToast({
        type: 'error',
        title: 'Download Failed',
        message,
      });
    }
  };

  return (
    <Modal
      isOpen={manualModalOpen}
      onClose={handleClose}
      title={
        <div className="flex items-center gap-2">
          <Download className="w-5 h-5 text-indigo-400" />
          <span>Manual Download Trigger</span>
        </div>
      }
      description="Queue an individual APK release URL for autonomous resolution, extraction, and staging."
      maxWidth="lg"
      showCloseButton={!manualDownloadMutation.isPending}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
            Target URL or Mobilism Topic <span className="text-rose-400">*</span>
          </label>
          <input
            type="url"
            name="url"
            value={formData.url}
            onChange={handleChange}
            required
            placeholder="https://forum.mobilism.org/viewtopic.php?t=... or direct mirror URL"
            className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              App Name (Optional)
            </label>
            <input
              type="text"
              name="app_name"
              value={formData.app_name || ''}
              onChange={handleChange}
              placeholder="Auto-detected if empty"
              className="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Version (Optional)
            </label>
            <input
              type="text"
              name="version"
              value={formData.version || ''}
              onChange={handleChange}
              placeholder="e.g. 1.2.3"
              className="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Releaser (Optional)
            </label>
            <input
              type="text"
              name="releaser"
              value={formData.releaser || ''}
              onChange={handleChange}
              placeholder="e.g. Balatan"
              className="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Resolver Tier Preference
            </label>
            <select
              name="download_tier"
              value={formData.download_tier || ''}
              onChange={handleChange}
              className="w-full px-3.5 py-2 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            >
              <option value="">Auto-Detect (Best Tier)</option>
              <option value="real_debrid">Real-Debrid Only</option>
              <option value="jdownloader">JDownloader Only</option>
              <option value="direct">Direct HTTP Only</option>
            </select>
          </div>
        </div>

        <div className="pt-4 flex items-center justify-end gap-3 border-t border-slate-800/80">
          <button
            type="button"
            onClick={handleClose}
            disabled={manualDownloadMutation.isPending}
            className="px-4 py-2 rounded-xl text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 transition disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={manualDownloadMutation.isPending}
            className="px-5 py-2 rounded-xl text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/25 transition flex items-center gap-2 disabled:opacity-50"
          >
            {manualDownloadMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Processing...</span>
              </>
            ) : (
              <>
                <Download className="w-4 h-4" />
                <span>Trigger Download</span>
              </>
            )}
          </button>
        </div>
      </form>
    </Modal>
  );
};

export default ManualDownloadModal;
