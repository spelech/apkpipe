import React from 'react';
import { CheckCircle, AlertCircle, Info, AlertTriangle, X } from 'lucide-react';
import { useToastStore, Toast } from '../../stores/useToastStore';

const toastConfig: Record<
  Toast['type'],
  {
    icon: React.ComponentType<{ className?: string }>;
    iconColor: string;
    borderColor: string;
    bgColor: string;
  }
> = {
  success: {
    icon: CheckCircle,
    iconColor: 'text-emerald-400',
    borderColor: 'border-emerald-500/30',
    bgColor: 'bg-emerald-950/40',
  },
  error: {
    icon: AlertCircle,
    iconColor: 'text-rose-400',
    borderColor: 'border-rose-500/30',
    bgColor: 'bg-rose-950/40',
  },
  warning: {
    icon: AlertTriangle,
    iconColor: 'text-amber-400',
    borderColor: 'border-amber-500/30',
    bgColor: 'bg-amber-950/40',
  },
  info: {
    icon: Info,
    iconColor: 'text-sky-400',
    borderColor: 'border-sky-500/30',
    bgColor: 'bg-sky-950/40',
  },
};

export const ToastContainer: React.FC = () => {
  const toasts = useToastStore((state) => state.toasts);
  const removeToast = useToastStore((state) => state.removeToast);

  if (toasts.length === 0) return null;

  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="fixed top-4 right-4 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none px-4 sm:px-0"
    >
      {toasts.map((toast) => {
        const config = toastConfig[toast.type] || toastConfig.info;
        const Icon = config.icon;

        return (
          <div
            key={toast.id}
            role="alert"
            className={`pointer-events-auto flex items-start gap-3 p-4 rounded-xl border ${config.borderColor} ${config.bgColor} glass-panel shadow-xl shadow-black/40 transition-all duration-300`}
          >
            <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${config.iconColor}`} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-slate-100 leading-tight">
                {toast.title}
              </p>
              {toast.message && (
                <p className="text-xs text-slate-300 mt-1 leading-relaxed break-words">
                  {toast.message}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => removeToast(toast.id)}
              className="text-slate-400 hover:text-slate-200 transition-colors p-1 -mr-1 -mt-1 rounded-lg hover:bg-white/10 shrink-0"
              aria-label="Dismiss notification"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
};

export default ToastContainer;
