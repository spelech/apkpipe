import React from 'react';
import { Navbar } from './Navbar';
import { ToastContainer } from '../common/ToastContainer';

export interface LayoutProps {
  children?: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <div className="bg-slate-950 text-slate-100 flex flex-col min-h-screen antialiased selection:bg-indigo-500 selection:text-white">
      {/* Toast Notification Stack */}
      <ToastContainer />

      {/* Main Top Navigation Header */}
      <Navbar />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>

      {/* Application Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-950 text-slate-500 py-6 text-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-500" />
            <span>APKPipe • Autonomous Homelab Ingestion</span>
          </div>

          <div className="flex items-center gap-4 text-slate-400">
            <span>Real-Debrid &amp; JDownloader Enabled</span>
            <span>•</span>
            <a
              href="https://github.com/spelech/apkpipe"
              target="_blank"
              rel="noreferrer"
              className="hover:text-slate-200 underline transition-colors"
            >
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Layout;
