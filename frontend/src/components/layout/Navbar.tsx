import React, { useState } from 'react';
import { NavLink, Link } from 'react-router-dom';
import {
  LayoutDashboard,
  BookmarkCheck,
  Rss,
  History,
  Settings,
  Plus,
  FileCode,
  Menu,
  X,
} from 'lucide-react';
import { useSystemStatusQuery } from '../../api';
import { useUIStore } from '../../stores';

interface NavItem {
  name: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  end?: boolean;
}

const navItems: NavItem[] = [
  { name: 'Dashboard', path: '/', icon: LayoutDashboard, end: true },
  { name: 'Watchlist', path: '/watchlist', icon: BookmarkCheck },
  { name: 'Feeds', path: '/feeds', icon: Rss },
  { name: 'Queue & History', path: '/history', icon: History },
  { name: 'Settings', path: '/settings', icon: Settings },
];

export const Navbar: React.FC = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const setManualModalOpen = useUIStore((state) => state.setManualModalOpen);
  const { data: health, isLoading: isHealthLoading, isError: isHealthError } = useSystemStatusQuery(15000);

  const getHealthBadge = () => {
    if (isHealthLoading) {
      return (
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-800/80 border border-slate-700/60 text-xs text-slate-400">
          <span className="w-2 h-2 rounded-full bg-slate-500 animate-pulse" />
          <span className="hidden sm:inline">Connecting...</span>
        </div>
      );
    }

    if (isHealthError || !health) {
      return (
        <div
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-950/50 border border-rose-500/30 text-xs text-rose-300"
          title="Backend API is unreachable"
        >
          <span className="w-2 h-2 rounded-full bg-rose-500" />
          <span className="hidden sm:inline">Offline</span>
        </div>
      );
    }

    const isHealthy =
      health.status?.toLowerCase() === 'ok' ||
      health.status?.toLowerCase() === 'healthy';

    return (
      <div
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono border ${
          isHealthy
            ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300'
            : 'bg-amber-950/40 border-amber-500/30 text-amber-300'
        }`}
        title={`Status: ${health.status} | Version: v${health.version}${
          health.active_tasks !== undefined ? ` | Active: ${health.active_tasks}` : ''
        }`}
      >
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${
            isHealthy ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
          }`}
        />
        <span className="hidden sm:inline font-sans">
          {isHealthy ? 'Healthy' : health.status}
        </span>
        <span className="text-[10px] text-slate-400 font-mono">
          v{health.version}
        </span>
      </div>
    );
  };

  return (
    <header className="sticky top-0 z-40 bg-slate-900/80 backdrop-blur-md border-b border-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Left: Brand & Desktop Navigation */}
          <div className="flex items-center gap-8">
            <Link to="/" className="flex items-center gap-3 group">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-sky-400 flex items-center justify-center shadow-lg shadow-indigo-500/20 group-hover:scale-105 transition-transform">
                <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M17.523 15.3414c-.5511 0-.9993-.4486-.9993-.9997s.4482-.9993.9993-.9993c.551 0 .9993.4482.9993.9993s-.4483.9997-.9993.9997m-11.046 0c-.5511 0-.9993-.4486-.9993-.9997s.4482-.9993.9993-.9993c.5511 0 .9993.4482.9993.9993s-.4482.9997-.9993.9997m11.4045-6.02l1.9973-3.4592a.416.416 0 00-.1523-.5676.416.416 0 00-.5676.1523l-2.0223 3.503C15.5902 8.4116 13.8533 8.087 12 8.087s-3.5902.3246-5.1367.8629L4.841 5.4469a.416.416 0 00-.5676-.1523.416.416 0 00-.1523.5676l1.9973 3.4592C2.6889 11.1867.3431 14.6589 0 18.7778h24c-.3431-4.1189-2.6889-7.5911-6.1185-9.4564" />
                </svg>
              </div>
              <div className="flex flex-col">
                <span className="text-lg font-bold bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent tracking-tight">
                  APKPipe
                </span>
                <span className="text-[10px] uppercase font-mono tracking-widest text-indigo-400 -mt-1">
                  Media Pipeline
                </span>
              </div>
            </Link>

            {/* Desktop Nav Links */}
            <nav className="hidden md:flex items-center space-x-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.end}
                    className={({ isActive }) =>
                      `flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm font-medium transition ${
                        isActive
                          ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 font-semibold shadow-sm'
                          : 'text-slate-300 hover:text-white hover:bg-slate-800/60 border border-transparent'
                      }`
                    }
                  >
                    <Icon className="w-4 h-4" />
                    <span>{item.name}</span>
                  </NavLink>
                );
              })}
            </nav>
          </div>

          {/* Right Header Actions */}
          <div className="flex items-center gap-3">
            {/* System Status Health Indicator */}
            {getHealthBadge()}

            {/* API Docs link */}
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="hidden lg:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-slate-400 hover:text-slate-200 bg-slate-800/50 hover:bg-slate-800 border border-slate-700/50 transition"
              title="Interactive OpenAPI / Swagger Documentation"
            >
              <FileCode className="w-3.5 h-3.5" />
              <span>API Docs</span>
            </a>

            {/* Manual Download Trigger Button */}
            <button
              type="button"
              onClick={() => setManualModalOpen(true)}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm font-semibold bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white shadow-lg shadow-indigo-500/25 transition transform active:scale-95 shrink-0"
            >
              <Plus className="w-4 h-4" />
              <span className="hidden sm:inline">Manual Download</span>
            </button>

            {/* Mobile Hamburger Button */}
            <button
              type="button"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition"
              aria-label="Toggle navigation menu"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Navigation Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden border-t border-slate-800 bg-slate-900/95 backdrop-blur-lg px-4 pt-3 pb-4 space-y-1 animate-fadeIn">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.end}
                onClick={() => setMobileMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition ${
                    isActive
                      ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 font-semibold'
                      : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
                  }`
                }
              >
                <Icon className="w-4 h-4" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}

          <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between px-3 text-xs text-slate-400">
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 hover:text-slate-200 py-1"
            >
              <FileCode className="w-3.5 h-3.5" />
              <span>Swagger API Docs</span>
            </a>
          </div>
        </div>
      )}
    </header>
  );
};

export default Navbar;
