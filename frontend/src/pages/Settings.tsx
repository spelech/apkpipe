import React, { useEffect, useState } from 'react';
import {
  Settings as SettingsIcon,
  Zap,
  HardDrive,
  Cloud,
  Bell,
  Save,
  Loader2,
  Eye,
  EyeOff,
  CheckCircle2,
  ExternalLink,
} from 'lucide-react';
import { useSettingsQuery, useUpdateSettingsMutation } from '../api';
import { useToastStore } from '../stores';
import type { AppSettings, SettingsUpdateRequest } from '../api/types';


const defaultSettings: AppSettings = {
  app_name: 'APKPipe',
  debug: false,
  download_dir: '/data/apkpipe/downloads',
  staging_dir: '/data/apkpipe/staging',
  poll_interval_seconds: 300,
  real_debrid_api_token: '',
  alldebrid_api_key: '',
  alldebrid_agent: 'apkpipe',
  jdownloader_email: '',
  jdownloader_password: '',
  jdownloader_device_name: '',
  jdownloader_watch_dir: '/data/jdownloader/watch',
  scraper_url: 'http://localhost:3000',
  nextcloud_url: '',
  nextcloud_token: '',
  nextcloud_occ_command: 'occ files:scan --all',
  apprise_url: '',
  ntfy_topic: '',
};

export const Settings: React.FC = () => {
  const [form, setForm] = useState<AppSettings>(defaultSettings);

  // Password / Secret visibility toggles
  const [showRdToken, setShowRdToken] = useState(false);
  const [showAdApiKey, setShowAdApiKey] = useState(false);
  const [showJdPass, setShowJdPass] = useState(false);
  const [showNcToken, setShowNcToken] = useState(false);

  const addToast = useToastStore((state) => state.addToast);

  const { data: settings, isLoading, isError } = useSettingsQuery();
  const updateMutation = useUpdateSettingsMutation();
  const isSaving = updateMutation.isPending;

  useEffect(() => {
    if (settings) {
      setForm({
        ...defaultSettings,
        ...settings,
      });
    }
  }, [settings]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
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

    const payload: SettingsUpdateRequest = {
      app_name: form.app_name.trim() || 'APKPipe',
      debug: form.debug,
      download_dir: form.download_dir.trim(),
      staging_dir: form.staging_dir.trim(),
      poll_interval_seconds: Math.max(10, form.poll_interval_seconds || 300),
      real_debrid_api_token: form.real_debrid_api_token?.trim() || '',
      alldebrid_api_key: form.alldebrid_api_key?.trim() || '',
      alldebrid_agent: form.alldebrid_agent?.trim() || 'apkpipe',
      jdownloader_email: form.jdownloader_email?.trim() || '',
      jdownloader_password: form.jdownloader_password || '',
      jdownloader_device_name: form.jdownloader_device_name?.trim() || '',
      jdownloader_watch_dir: form.jdownloader_watch_dir?.trim() || '',
      scraper_url: form.scraper_url?.trim() || '',
      nextcloud_url: form.nextcloud_url?.trim() || '',
      nextcloud_token: form.nextcloud_token || '',
      nextcloud_occ_command: form.nextcloud_occ_command?.trim() || '',
      apprise_url: form.apprise_url?.trim() || '',
      ntfy_topic: form.ntfy_topic?.trim() || '',
    };

    try {
      await updateMutation.mutateAsync(payload);
      addToast({
        type: 'success',
        title: 'Settings Saved',
        message: 'Successfully updated runtime configuration.',
      });
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Save Failed',
        message: err?.message || 'Failed to update settings',
      });
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              Runtime Settings
            </h1>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Configure resolver API keys, scraper endpoints, Nextcloud storage, and notification channels.
          </p>
        </div>

        <button
          type="button"
          onClick={handleSubmit}
          disabled={isSaving || isLoading}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/25 transition transform active:scale-95 disabled:opacity-50 shrink-0 self-start sm:self-auto"
        >
          {isSaving ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Saving...</span>
            </>
          ) : (
            <>
              <Save className="w-4 h-4" />
              <span>Save Settings</span>
            </>
          )}
        </button>
      </div>

      {isLoading ? (
        <div className="glass-panel p-16 rounded-2xl border border-slate-800 text-center text-slate-400">
          <div className="inline-flex items-center gap-2.5 text-sm text-indigo-400">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span>Loading current configuration...</span>
          </div>
        </div>
      ) : isError ? (
        <div className="glass-panel p-12 rounded-2xl border border-rose-500/30 bg-rose-950/20 text-center text-rose-300">
          <p className="font-semibold text-base">Failed to fetch settings from backend</p>
          <p className="text-xs text-rose-400 mt-1">Please ensure the backend service is running.</p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Section 1: General Pipeline Configuration */}
          <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4 shadow-xl">
            <h2 className="text-base font-bold text-white flex items-center gap-2.5 border-b border-slate-800 pb-3">
              <SettingsIcon className="w-5 h-5 text-indigo-400" />
              <span>General Pipeline</span>
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Application Name
                </label>
                <input
                  type="text"
                  name="app_name"
                  value={form.app_name}
                  onChange={handleChange}
                  placeholder="APKPipe"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Background Poll Interval (Seconds)
                </label>
                <input
                  type="number"
                  name="poll_interval_seconds"
                  value={form.poll_interval_seconds}
                  onChange={handleChange}
                  min={10}
                  placeholder="300"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Download Target Directory
                </label>
                <input
                  type="text"
                  name="download_dir"
                  value={form.download_dir}
                  onChange={handleChange}
                  placeholder="/data/apkpipe/downloads"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Staging / Working Directory
                </label>
                <input
                  type="text"
                  name="staging_dir"
                  value={form.staging_dir}
                  onChange={handleChange}
                  placeholder="/data/apkpipe/staging"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
                />
              </div>
            </div>

            <div className="flex items-center gap-3 pt-2">
              <input
                type="checkbox"
                id="settings_debug_checkbox"
                name="debug"
                checked={form.debug}
                onChange={handleChange}
                className="w-4 h-4 rounded bg-slate-950 border-slate-700 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-slate-900 cursor-pointer"
              />
              <label
                htmlFor="settings_debug_checkbox"
                className="text-sm font-medium text-slate-300 cursor-pointer select-none"
              >
                Enable verbose debug logging and stack traces
              </label>
            </div>
          </div>

          {/* Section 2: Real-Debrid Tier 1 Resolver */}
          <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4 shadow-xl">
            <h2 className="text-base font-bold text-white flex items-center gap-2.5 border-b border-slate-800 pb-3">
              <Zap className="w-5 h-5 text-indigo-400" />
              <span>Real-Debrid Tier 1 Resolver</span>
            </h2>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                Real-Debrid API Token
              </label>
              <div className="relative">
                <input
                  type={showRdToken ? 'text' : 'password'}
                  name="real_debrid_api_token"
                  value={form.real_debrid_api_token}
                  onChange={handleChange}
                  placeholder="Paste your Real-Debrid API token here"
                  className="w-full pl-3.5 pr-24 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
                />
                <button
                  type="button"
                  onClick={() => setShowRdToken(!showRdToken)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-indigo-400 hover:text-indigo-300 flex items-center gap-1 px-2 py-1 rounded bg-slate-900 border border-slate-700/60 transition"
                >
                  {showRdToken ? (
                    <>
                      <EyeOff className="w-3.5 h-3.5" />
                      <span>Hide</span>
                    </>
                  ) : (
                    <>
                      <Eye className="w-3.5 h-3.5" />
                      <span>Show</span>
                    </>
                  )}
                </button>
              </div>
              <p className="text-xs text-slate-500 mt-1.5">
                Required for unthrottled premium multi-hoster unrestrict unzipping and high-speed downloads.
              </p>
            </div>
          </div>

          {/* Section 3: AllDebrid Tier 1b Resolver */}
          <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-base font-bold text-white flex items-center gap-2.5">
                <Zap className="w-5 h-5 text-purple-400" />
                <span>AllDebrid Resolver (Tier 1b)</span>
              </h2>
              <a
                href="https://alldebrid.com/apikeys/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1 transition"
              >
                <span>Get API Key</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                AllDebrid API Key
              </label>
              <div className="relative">
                <input
                  type={showAdApiKey ? 'text' : 'password'}
                  name="alldebrid_api_key"
                  value={form.alldebrid_api_key || ''}
                  onChange={handleChange}
                  placeholder="Paste your AllDebrid API key here"
                  className="w-full pl-3.5 pr-24 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition"
                />
                <button
                  type="button"
                  onClick={() => setShowAdApiKey(!showAdApiKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-purple-400 hover:text-purple-300 flex items-center gap-1 px-2 py-1 rounded bg-slate-900 border border-slate-700/60 transition"
                >
                  {showAdApiKey ? (
                    <>
                      <EyeOff className="w-3.5 h-3.5" />
                      <span>Hide</span>
                    </>
                  ) : (
                    <>
                      <Eye className="w-3.5 h-3.5" />
                      <span>Show</span>
                    </>
                  )}
                </button>
              </div>
              <p className="text-xs text-slate-500 mt-1.5">
                Tier 1b peer multi-hoster resolver. Works alongside Real-Debrid with peer fallthrough to maximize hoster coverage (1fichier, rapidgator, uptobox, mega, etc.).
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                AllDebrid Client Agent Identifier
              </label>
              <input
                type="text"
                name="alldebrid_agent"
                value={form.alldebrid_agent || ''}
                onChange={handleChange}
                placeholder="apkpipe"
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition"
              />
              <p className="text-xs text-slate-500 mt-1.5">
                Identifier passed to the AllDebrid API in the agent parameter (defaults to apkpipe).
              </p>
            </div>
          </div>

          {/* Section 4: JDownloader Tier 2 Fallback */}
          <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4 shadow-xl">
            <h2 className="text-base font-bold text-white flex items-center gap-2.5 border-b border-slate-800 pb-3">
              <HardDrive className="w-5 h-5 text-pink-400" />
              <span>JDownloader Tier 2 Fallback</span>
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  MyJDownloader Email
                </label>
                <input
                  type="email"
                  name="jdownloader_email"
                  value={form.jdownloader_email}
                  onChange={handleChange}
                  placeholder="user@example.com"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  MyJDownloader Password
                </label>
                <div className="relative">
                  <input
                    type={showJdPass ? 'text' : 'password'}
                    name="jdownloader_password"
                    value={form.jdownloader_password || ''}
                    onChange={handleChange}
                    placeholder="••••••••••••"
                    className="w-full pl-3.5 pr-24 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowJdPass(!showJdPass)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-pink-400 hover:text-pink-300 flex items-center gap-1 px-2 py-1 rounded bg-slate-900 border border-slate-700/60 transition"
                  >
                    {showJdPass ? (
                      <>
                        <EyeOff className="w-3.5 h-3.5" />
                        <span>Hide</span>
                      </>
                    ) : (
                      <>
                        <Eye className="w-3.5 h-3.5" />
                        <span>Show</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Device Name
                </label>
                <input
                  type="text"
                  name="jdownloader_device_name"
                  value={form.jdownloader_device_name}
                  onChange={handleChange}
                  placeholder="e.g. Home-JDownloader"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Watch Directory / DLC Ingest Folder
                </label>
                <input
                  type="text"
                  name="jdownloader_watch_dir"
                  value={form.jdownloader_watch_dir}
                  onChange={handleChange}
                  placeholder="/data/jdownloader/watch"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
                />
              </div>
            </div>
          </div>

          {/* Section 5: Scraper Microservice & Nextcloud OCC */}
          <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4 shadow-xl">
            <h2 className="text-base font-bold text-white flex items-center gap-2.5 border-b border-slate-800 pb-3">
              <Cloud className="w-5 h-5 text-sky-400" />
              <span>Scraper &amp; Nextcloud Ingestion</span>
            </h2>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                Playwright Scraper Microservice URL
              </label>
              <input
                type="url"
                name="scraper_url"
                value={form.scraper_url}
                onChange={handleChange}
                placeholder="http://localhost:3000"
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Nextcloud Server URL
                </label>
                <input
                  type="url"
                  name="nextcloud_url"
                  value={form.nextcloud_url}
                  onChange={handleChange}
                  placeholder="https://nextcloud.homelab.local"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Nextcloud API Token
                </label>
                <div className="relative">
                  <input
                    type={showNcToken ? 'text' : 'password'}
                    name="nextcloud_token"
                    value={form.nextcloud_token || ''}
                    onChange={handleChange}
                    placeholder="••••••••••••"
                    className="w-full pl-3.5 pr-24 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNcToken(!showNcToken)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-sky-400 hover:text-sky-300 flex items-center gap-1 px-2 py-1 rounded bg-slate-900 border border-slate-700/60 transition"
                  >
                    {showNcToken ? (
                      <>
                        <EyeOff className="w-3.5 h-3.5" />
                        <span>Hide</span>
                      </>
                    ) : (
                      <>
                        <Eye className="w-3.5 h-3.5" />
                        <span>Show</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                Nextcloud OCC Scan Command
              </label>
              <input
                type="text"
                name="nextcloud_occ_command"
                value={form.nextcloud_occ_command}
                onChange={handleChange}
                placeholder="occ files:scan --all or docker exec nextcloud occ files:scan --all"
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
              />
            </div>
          </div>

          {/* Section 6: Notifications */}
          <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4 shadow-xl">
            <h2 className="text-base font-bold text-white flex items-center gap-2.5 border-b border-slate-800 pb-3">
              <Bell className="w-5 h-5 text-amber-400" />
              <span>Notifications (Apprise &amp; Ntfy)</span>
            </h2>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                Apprise Gateway URL
              </label>
              <input
                type="text"
                name="apprise_url"
                value={form.apprise_url}
                onChange={handleChange}
                placeholder="e.g. tgram://bottoken/chatid or discord://webhook_id/token"
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                Ntfy Topic / Endpoint
              </label>
              <input
                type="text"
                name="ntfy_topic"
                value={form.ntfy_topic}
                onChange={handleChange}
                placeholder="https://ntfy.sh/my_homelab_apkpipe"
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-700/80 text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
              />
            </div>
          </div>

          {/* Bottom Save Button */}
          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={isSaving}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-base font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-xl shadow-indigo-600/25 transition transform active:scale-95 disabled:opacity-50"
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>Saving Settings...</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-5 h-5" />
                  <span>Save All Settings</span>
                </>
              )}
            </button>
          </div>
        </form>
      )}
    </div>
  );
};

export default Settings;

