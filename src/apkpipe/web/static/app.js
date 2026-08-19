/**
 * APKPipe Web Dashboard - Alpine.js Application Logic
 */

// Toast notification helper
window.showToast = function(message, type = 'info', duration = 4000) {
  window.dispatchEvent(new CustomEvent('app-toast', {
    detail: { message, type, duration, id: Date.now() + Math.random() }
  }));
};

// Global formatting utilities
function formatBytes(bytes, decimals = 2) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function formatDate(isoStr) {
  if (!isoStr) return 'Never';
  try {
    const d = new Date(isoStr);
    return isNaN(d.getTime()) ? isoStr : d.toLocaleString();
  } catch (e) {
    return isoStr;
  }
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '-';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const remSecs = Math.round(seconds % 60);
  return `${mins}m ${remSecs}s`;
}

// Global API fetch wrapper
async function apiFetch(url, options = {}) {
  try {
    const res = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        ...(options.headers || {})
      },
      ...options
    });
    if (!res.ok) {
      let errorMsg = `HTTP ${res.status}: ${res.statusText}`;
      try {
        const errorData = await res.json();
        if (errorData.detail) {
          errorMsg = typeof errorData.detail === 'string' 
            ? errorData.detail 
            : JSON.stringify(errorData.detail);
        }
      } catch (_) {}
      throw new Error(errorMsg);
    }
    return await res.json();
  } catch (err) {
    console.error(`API Error on ${url}:`, err);
    throw err;
  }
}

// -------------------------------------------------------------
// Toast Component Store / Controller
// -------------------------------------------------------------
function toastStore() {
  return {
    toasts: [],
    init() {
      window.addEventListener('app-toast', (e) => {
        const toast = e.detail;
        this.toasts.push(toast);
        setTimeout(() => {
          this.remove(toast.id);
        }, toast.duration || 4000);
      });
    },
    remove(id) {
      this.toasts = this.toasts.filter(t => t.id !== id);
    }
  };
}

// -------------------------------------------------------------
// Dashboard Application Component
// -------------------------------------------------------------
function dashboardApp() {
  return {
    loading: true,
    stats: {
      activeWatchlist: 0,
      totalWatchlist: 0,
      activeFeeds: 0,
      totalFeeds: 0,
      totalDownloads: 0,
      systemStatus: 'healthy',
      version: '0.1.0'
    },
    recentTasks: [],
    recentHistory: [],
    // Manual Download Modal
    manualModalOpen: false,
    manualSubmitting: false,
    manualForm: {
      url: '',
      app_name: '',
      version: '',
      releaser: '',
      category: 'Apps',
      download_tier: '',
      auto_resolve: true,
      trigger_ingest: true
    },

    async init() {
      await this.refreshData();
      // Auto refresh every 10 seconds
      setInterval(() => this.refreshData(false), 10000);
    },

    async refreshData(showLoading = true) {
      if (showLoading) this.loading = true;
      try {
        const [watchlist, feeds, queue, history, health] = await Promise.allSettled([
          apiFetch('/api/watchlist'),
          apiFetch('/api/feeds'),
          apiFetch('/api/downloads/queue?limit=10'),
          apiFetch('/api/downloads/history?limit=10'),
          apiFetch('/health')
        ]);

        if (watchlist.status === 'fulfilled') {
          const items = watchlist.value;
          this.stats.totalWatchlist = items.length;
          this.stats.activeWatchlist = items.filter(i => i.enabled).length;
        }

        if (feeds.status === 'fulfilled') {
          const items = feeds.value;
          this.stats.totalFeeds = items.length;
          this.stats.activeFeeds = items.filter(f => f.enabled).length;
        }

        if (history.status === 'fulfilled') {
          const hist = history.value;
          this.stats.totalDownloads = hist.filter(h => h.status === 'completed').length;
          this.recentHistory = hist;
        }

        if (queue.status === 'fulfilled') {
          this.recentTasks = queue.value;
        }

        if (health.status === 'fulfilled') {
          this.stats.systemStatus = health.value.status || 'healthy';
          this.stats.version = health.value.version || '0.1.0';
        }
      } catch (err) {
        console.error('Error fetching dashboard stats:', err);
      } finally {
        this.loading = false;
      }
    },

    openManualModal() {
      this.manualForm = {
        url: '',
        app_name: '',
        version: '',
        releaser: '',
        category: 'Apps',
        download_tier: '',
        auto_resolve: true,
        trigger_ingest: true
      };
      this.manualModalOpen = true;
    },

    closeManualModal() {
      this.manualModalOpen = false;
    },

    async submitManualDownload() {
      if (!this.manualForm.url) {
        showToast('Please enter a download or topic URL', 'warning');
        return;
      }
      this.manualSubmitting = true;
      try {
        const payload = { ...this.manualForm };
        if (!payload.download_tier) delete payload.download_tier;
        if (!payload.app_name) delete payload.app_name;
        if (!payload.version) delete payload.version;
        if (!payload.releaser) delete payload.releaser;

        const res = await apiFetch('/api/downloads/manual', {
          method: 'POST',
          body: JSON.stringify(payload)
        });

        showToast(`Manual task initiated for ${res.feed_item_title || 'APK'}!`, 'success');
        this.closeManualModal();
        await this.refreshData();
      } catch (err) {
        showToast(`Failed to trigger manual download: ${err.message}`, 'error');
      } finally {
        this.manualSubmitting = false;
      }
    },

    async retryTask(taskId) {
      try {
        await apiFetch(`/api/downloads/${taskId}/retry`, { method: 'POST' });
        showToast(`Task #${taskId} retry queued`, 'success');
        await this.refreshData();
      } catch (err) {
        showToast(`Retry failed: ${err.message}`, 'error');
      }
    }
  };
}

// -------------------------------------------------------------
// Watchlist Application Component
// -------------------------------------------------------------
function watchlistApp() {
  return {
    items: [],
    loading: true,
    searchQuery: '',
    categoryFilter: '',
    statusFilter: '',
    // Modal state
    modalOpen: false,
    modalMode: 'add', // 'add' or 'edit'
    saving: false,
    form: {
      id: null,
      app_name: '',
      package_name: '',
      title_regex: '',
      min_version: '0.0.0',
      category: 'Apps',
      releaser_whitelist_raw: '',
      releaser_blacklist_raw: '',
      enabled: true
    },

    get filteredItems() {
      return this.items.filter(item => {
        const matchesSearch = !this.searchQuery || 
          item.app_name.toLowerCase().includes(this.searchQuery.toLowerCase()) ||
          (item.package_name && item.package_name.toLowerCase().includes(this.searchQuery.toLowerCase()));
        const matchesCat = !this.categoryFilter || item.category === this.categoryFilter;
        const matchesStatus = !this.statusFilter || 
          (this.statusFilter === 'enabled' && item.enabled) ||
          (this.statusFilter === 'disabled' && !item.enabled);
        return matchesSearch && matchesCat && matchesStatus;
      });
    },

    get categories() {
      const cats = new Set(this.items.map(i => i.category).filter(Boolean));
      return Array.from(cats).sort();
    },

    async init() {
      await this.loadItems();
    },

    async loadItems() {
      this.loading = true;
      try {
        this.items = await apiFetch('/api/watchlist');
      } catch (err) {
        showToast(`Failed to load watchlist: ${err.message}`, 'error');
      } finally {
        this.loading = false;
      }
    },

    openAddModal() {
      this.modalMode = 'add';
      this.form = {
        id: null,
        app_name: '',
        package_name: '',
        title_regex: '',
        min_version: '0.0.0',
        category: 'Apps',
        releaser_whitelist_raw: '',
        releaser_blacklist_raw: '',
        enabled: true
      };
      this.modalOpen = true;
    },

    openEditModal(item) {
      this.modalMode = 'edit';
      this.form = {
        id: item.id,
        app_name: item.app_name,
        package_name: item.package_name || '',
        title_regex: item.title_regex || '',
        min_version: item.min_version || '0.0.0',
        category: item.category || 'Apps',
        releaser_whitelist_raw: (item.releaser_whitelist || []).join(', '),
        releaser_blacklist_raw: (item.releaser_blacklist || []).join(', '),
        enabled: item.enabled
      };
      this.modalOpen = true;
    },

    closeModal() {
      this.modalOpen = false;
    },

    async saveItem() {
      if (!this.form.app_name.trim()) {
        showToast('App Name is required', 'warning');
        return;
      }

      this.saving = true;
      try {
        const whitelist = this.form.releaser_whitelist_raw
          ? this.form.releaser_whitelist_raw.split(',').map(s => s.trim()).filter(Boolean)
          : [];
        const blacklist = this.form.releaser_blacklist_raw
          ? this.form.releaser_blacklist_raw.split(',').map(s => s.trim()).filter(Boolean)
          : [];

        const payload = {
          app_name: this.form.app_name.trim(),
          package_name: this.form.package_name.trim() || null,
          title_regex: this.form.title_regex.trim() || null,
          min_version: this.form.min_version.trim() || '0.0.0',
          category: this.form.category.trim() || 'Apps',
          releaser_whitelist: whitelist,
          releaser_blacklist: blacklist,
          enabled: this.form.enabled
        };

        if (this.modalMode === 'add') {
          await apiFetch('/api/watchlist', {
            method: 'POST',
            body: JSON.stringify(payload)
          });
          showToast(`Added '${payload.app_name}' to watchlist`, 'success');
        } else {
          await apiFetch(`/api/watchlist/${this.form.id}`, {
            method: 'PUT',
            body: JSON.stringify(payload)
          });
          showToast(`Updated '${payload.app_name}'`, 'success');
        }

        this.closeModal();
        await this.loadItems();
      } catch (err) {
        showToast(`Save failed: ${err.message}`, 'error');
      } finally {
        this.saving = false;
      }
    },

    async toggleEnabled(item) {
      const updatedStatus = !item.enabled;
      try {
        await apiFetch(`/api/watchlist/${item.id}`, {
          method: 'PUT',
          body: JSON.stringify({ enabled: updatedStatus })
        });
        item.enabled = updatedStatus;
        showToast(`${item.app_name} is now ${updatedStatus ? 'enabled' : 'disabled'}`, 'info');
      } catch (err) {
        showToast(`Failed to update status: ${err.message}`, 'error');
      }
    },

    async deleteItem(item) {
      if (!confirm(`Are you sure you want to delete '${item.app_name}' from watchlist?`)) {
        return;
      }
      try {
        await apiFetch(`/api/watchlist/${item.id}`, { method: 'DELETE' });
        showToast(`Removed '${item.app_name}'`, 'success');
        this.items = this.items.filter(i => i.id !== item.id);
      } catch (err) {
        showToast(`Delete failed: ${err.message}`, 'error');
      }
    }
  };
}

// -------------------------------------------------------------
// Feeds Application Component
// -------------------------------------------------------------
function feedsApp() {
  return {
    feeds: [],
    loading: true,
    pollingAll: false,
    pollingId: null,
    // Modal state
    modalOpen: false,
    modalMode: 'add',
    saving: false,
    form: {
      id: null,
      name: '',
      url: '',
      feed_type: 'mobilism_rss',
      poll_interval_minutes: 15,
      enabled: true
    },

    async init() {
      await this.loadFeeds();
    },

    async loadFeeds() {
      this.loading = true;
      try {
        this.feeds = await apiFetch('/api/feeds');
      } catch (err) {
        showToast(`Failed to load feeds: ${err.message}`, 'error');
      } finally {
        this.loading = false;
      }
    },

    openAddModal() {
      this.modalMode = 'add';
      this.form = {
        id: null,
        name: '',
        url: '',
        feed_type: 'mobilism_rss',
        poll_interval_minutes: 15,
        enabled: true
      };
      this.modalOpen = true;
    },

    openEditModal(feed) {
      this.modalMode = 'edit';
      this.form = {
        id: feed.id,
        name: feed.name,
        url: feed.url,
        feed_type: feed.feed_type,
        poll_interval_minutes: feed.poll_interval_minutes,
        enabled: feed.enabled
      };
      this.modalOpen = true;
    },

    closeModal() {
      this.modalOpen = false;
    },

    async saveFeed() {
      if (!this.form.name.trim() || !this.form.url.trim()) {
        showToast('Feed Name and URL are required', 'warning');
        return;
      }

      this.saving = true;
      try {
        const payload = {
          name: this.form.name.trim(),
          url: this.form.url.trim(),
          feed_type: this.form.feed_type,
          poll_interval_minutes: parseInt(this.form.poll_interval_minutes, 10) || 15,
          enabled: this.form.enabled
        };

        if (this.modalMode === 'add') {
          await apiFetch('/api/feeds', {
            method: 'POST',
            body: JSON.stringify(payload)
          });
          showToast(`Added feed '${payload.name}'`, 'success');
        } else {
          await apiFetch(`/api/feeds/${this.form.id}`, {
            method: 'PUT',
            body: JSON.stringify(payload)
          });
          showToast(`Updated feed '${payload.name}'`, 'success');
        }

        this.closeModal();
        await this.loadFeeds();
      } catch (err) {
        showToast(`Save failed: ${err.message}`, 'error');
      } finally {
        this.saving = false;
      }
    },

    async toggleEnabled(feed) {
      const updatedStatus = !feed.enabled;
      try {
        await apiFetch(`/api/feeds/${feed.id}`, {
          method: 'PUT',
          body: JSON.stringify({ enabled: updatedStatus })
        });
        feed.enabled = updatedStatus;
        showToast(`${feed.name} is now ${updatedStatus ? 'enabled' : 'disabled'}`, 'info');
      } catch (err) {
        showToast(`Failed to update status: ${err.message}`, 'error');
      }
    },

    async deleteFeed(feed) {
      if (!confirm(`Delete feed source '${feed.name}'?`)) return;
      try {
        await apiFetch(`/api/feeds/${feed.id}`, { method: 'DELETE' });
        showToast(`Deleted '${feed.name}'`, 'success');
        this.feeds = this.feeds.filter(f => f.id !== feed.id);
      } catch (err) {
        showToast(`Delete failed: ${err.message}`, 'error');
      }
    },

    async pollSingle(feed) {
      this.pollingId = feed.id;
      try {
        const res = await apiFetch(`/api/feeds/${feed.id}/poll`, { method: 'POST' });
        showToast(`Polled ${feed.name}: ${res.new_items_found || res.matched_items || 0} matches processed`, 'success');
        await this.loadFeeds();
      } catch (err) {
        showToast(`Poll failed: ${err.message}`, 'error');
      } finally {
        this.pollingId = null;
      }
    },

    async pollAllFeeds() {
      this.pollingAll = true;
      try {
        const res = await apiFetch('/api/feeds/poll-all', { method: 'POST' });
        showToast(`Polled all feeds successfully! (${res.total_items_processed || 0} items checked)`, 'success');
        await this.loadFeeds();
      } catch (err) {
        showToast(`Poll All failed: ${err.message}`, 'error');
      } finally {
        this.pollingAll = false;
      }
    }
  };
}

// -------------------------------------------------------------
// History & Queue Application Component
// -------------------------------------------------------------
function historyApp() {
  return {
    activeTab: 'queue', // 'queue' or 'history'
    queue: [],
    history: [],
    loading: true,
    autoRefresh: true,
    searchQuery: '',
    statusFilter: '',
    refreshTimer: null,

    get filteredQueue() {
      return this.queue.filter(task => {
        const matchesSearch = !this.searchQuery || 
          (task.feed_item_title && task.feed_item_title.toLowerCase().includes(this.searchQuery.toLowerCase())) ||
          (task.matched_releaser && task.matched_releaser.toLowerCase().includes(this.searchQuery.toLowerCase()));
        const matchesStatus = !this.statusFilter || task.status === this.statusFilter;
        return matchesSearch && matchesStatus;
      });
    },

    get filteredHistory() {
      return this.history.filter(item => {
        const matchesSearch = !this.searchQuery || 
          (item.app_name && item.app_name.toLowerCase().includes(this.searchQuery.toLowerCase())) ||
          (item.releaser && item.releaser.toLowerCase().includes(this.searchQuery.toLowerCase()));
        const matchesStatus = !this.statusFilter || item.status === this.statusFilter;
        return matchesSearch && matchesStatus;
      });
    },

    async init() {
      await this.refreshAll();
      this.refreshTimer = setInterval(() => {
        if (this.autoRefresh) {
          this.refreshAll(false);
        }
      }, 5000);
    },

    async refreshAll(showLoading = true) {
      if (showLoading) this.loading = true;
      try {
        const [qRes, hRes] = await Promise.allSettled([
          apiFetch('/api/downloads/queue?limit=100'),
          apiFetch('/api/downloads/history?limit=100')
        ]);
        if (qRes.status === 'fulfilled') this.queue = qRes.value;
        if (hRes.status === 'fulfilled') this.history = hRes.value;
      } catch (err) {
        console.error('Error fetching history:', err);
      } finally {
        this.loading = false;
      }
    },

    async retryTask(task) {
      try {
        await apiFetch(`/api/downloads/${task.id}/retry`, { method: 'POST' });
        showToast(`Retrying task #${task.id}...`, 'success');
        await this.refreshAll();
      } catch (err) {
        showToast(`Retry failed: ${err.message}`, 'error');
      }
    },

    async deleteTask(task) {
      if (!confirm(`Cancel/remove download task #${task.id} (${task.feed_item_title})?`)) return;
      try {
        await apiFetch(`/api/downloads/${task.id}`, { method: 'DELETE' });
        showToast(`Removed task #${task.id}`, 'info');
        this.queue = this.queue.filter(t => t.id !== task.id);
      } catch (err) {
        showToast(`Delete failed: ${err.message}`, 'error');
      }
    }
  };
}

// -------------------------------------------------------------
// Settings Application Component
// -------------------------------------------------------------
function settingsApp() {
  return {
    loading: true,
    saving: false,
    showToken: false,
    showJdPass: false,
    form: {
      app_name: 'APKPipe',
      debug: false,
      download_dir: '/data/downloads',
      staging_dir: '/data/staging',
      poll_interval_seconds: 900,
      real_debrid_api_token: '',
      jdownloader_email: '',
      jdownloader_password: '',
      jdownloader_device_name: '',
      jdownloader_watch_dir: '',
      scraper_url: 'http://localhost:3000',
      nextcloud_url: '',
      nextcloud_token: '',
      nextcloud_occ_command: 'occ files:scan --all',
      apprise_url: '',
      ntfy_topic: ''
    },

    async init() {
      await this.loadSettings();
    },

    async loadSettings() {
      this.loading = true;
      try {
        const data = await apiFetch('/api/settings');
        this.form = { ...this.form, ...data };
      } catch (err) {
        showToast(`Failed to load settings: ${err.message}`, 'error');
      } finally {
        this.loading = false;
      }
    },

    async saveSettings() {
      this.saving = true;
      try {
        const payload = { ...this.form };
        if (payload.poll_interval_seconds) {
          payload.poll_interval_seconds = parseInt(payload.poll_interval_seconds, 10);
        }
        const updated = await apiFetch('/api/settings', {
          method: 'POST',
          body: JSON.stringify(payload)
        });
        this.form = { ...this.form, ...updated };
        showToast('Settings successfully updated!', 'success');
      } catch (err) {
        showToast(`Failed to update settings: ${err.message}`, 'error');
      } finally {
        this.saving = false;
      }
    }
  };
}
