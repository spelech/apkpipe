import React from 'react';
import { Modal } from './Modal';
import { AlertTriangle, AlertCircle, Info, Loader2 } from 'lucide-react';

export interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  title?: string;
  message?: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  variant?: 'danger' | 'warning' | 'info';
  isLoading?: boolean;
}

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title = 'Are you sure?',
  message = 'This action cannot be undone. Please confirm to proceed.',
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'danger',
  isLoading = false,
}) => {
  const getIcon = () => {
    switch (variant) {
      case 'danger':
        return <AlertTriangle className="w-6 h-6 text-rose-400" />;
      case 'warning':
        return <AlertCircle className="w-6 h-6 text-amber-400" />;
      case 'info':
      default:
        return <Info className="w-6 h-6 text-indigo-400" />;
    }
  };

  const getIconBg = () => {
    switch (variant) {
      case 'danger':
        return 'bg-rose-500/15 border-rose-500/30 text-rose-400';
      case 'warning':
        return 'bg-amber-500/15 border-amber-500/30 text-amber-400';
      case 'info':
      default:
        return 'bg-indigo-500/15 border-indigo-500/30 text-indigo-400';
    }
  };

  const getConfirmButtonClasses = () => {
    switch (variant) {
      case 'danger':
        return 'bg-rose-600 hover:bg-rose-500 text-white shadow-rose-600/20';
      case 'warning':
        return 'bg-amber-600 hover:bg-amber-500 text-white shadow-amber-600/20';
      case 'info':
      default:
        return 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/20';
    }
  };

  const handleConfirm = async () => {
    await onConfirm();
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} maxWidth="md" showCloseButton={!isLoading}>
      <div className="flex items-start gap-4">
        <div className={`p-3 rounded-2xl border ${getIconBg()} shrink-0 mt-0.5`}>
          {getIcon()}
        </div>

        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-bold text-white tracking-tight leading-snug">
            {title}
          </h3>
          <div className="mt-2 text-sm text-slate-300 leading-relaxed">
            {message}
          </div>
        </div>
      </div>

      <div className="mt-6 flex items-center justify-end gap-3 border-t border-slate-800/80 pt-4">
        <button
          type="button"
          onClick={onClose}
          disabled={isLoading}
          className="px-4 py-2 rounded-xl text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 transition disabled:opacity-50"
        >
          {cancelText}
        </button>

        <button
          type="button"
          onClick={handleConfirm}
          disabled={isLoading}
          className={`px-5 py-2 rounded-xl text-sm font-semibold shadow-lg transition flex items-center gap-2 disabled:opacity-50 ${getConfirmButtonClasses()}`}
        >
          {isLoading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Processing...</span>
            </>
          ) : (
            confirmText
          )}
        </button>
      </div>
    </Modal>
  );
};

export default ConfirmDialog;
