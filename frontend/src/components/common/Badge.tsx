import React from 'react';

export type BadgeStatus = 'pending' | 'resolving' | 'downloading' | 'completed' | 'failed' | string;
export type ResolverTier = 'real_debrid' | 'alldebrid' | 'jdownloader' | 'direct' | string;
export type BadgeVariant =
  | BadgeStatus
  | ResolverTier
  | 'default'
  | 'success'
  | 'warning'
  | 'error'
  | 'info';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  status?: BadgeStatus;
  tier?: ResolverTier;
  pulse?: boolean;
  size?: 'xs' | 'sm' | 'md';
  children?: React.ReactNode;
}

const variantStyles: Record<string, string> = {
  // Pipeline statuses
  pending: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  resolving: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  downloading: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  completed: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  failed: 'bg-rose-500/15 text-rose-400 border-rose-500/30',

  // Resolver tiers
  real_debrid: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
  'tier-rd': 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
  alldebrid: 'bg-purple-900/30 text-purple-400 border-purple-800/40',
  'tier-ad': 'bg-purple-900/30 text-purple-400 border-purple-800/40',
  'tier-alldebrid': 'bg-purple-900/30 text-purple-400 border-purple-800/40',
  jdownloader: 'bg-pink-500/15 text-pink-300 border-pink-500/30',
  'tier-jd': 'bg-pink-500/15 text-pink-300 border-pink-500/30',
  direct: 'bg-teal-500/15 text-teal-300 border-teal-500/30',
  'tier-direct': 'bg-teal-500/15 text-teal-300 border-teal-500/30',

  // Generic variants
  success: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  warning: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  error: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
  info: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  default: 'bg-slate-800/80 text-slate-300 border-slate-700/80',
};

const defaultLabels: Record<string, string> = {
  pending: 'Pending',
  resolving: 'Resolving',
  downloading: 'Downloading',
  completed: 'Completed',
  failed: 'Failed',
  real_debrid: 'Real-Debrid',
  alldebrid: 'AllDebrid',
  'tier-ad': 'AllDebrid',
  'tier-alldebrid': 'AllDebrid',
  jdownloader: 'JDownloader',
  direct: 'Direct HTTP',
};

const sizeStyles: Record<'xs' | 'sm' | 'md', string> = {
  xs: 'text-[10px] px-1.5 py-0.5',
  sm: 'text-xs px-2.5 py-0.5',
  md: 'text-sm px-3 py-1',
};

export const Badge: React.FC<BadgeProps> = ({
  variant,
  status,
  tier,
  pulse,
  size = 'sm',
  className = '',
  children,
  ...props
}) => {
  const key = (status || tier || variant || 'default').toLowerCase();
  const colorClasses = variantStyles[key] || variantStyles.default;
  const isPulsing =
    pulse ?? (key === 'resolving' || key === 'downloading');
  const label = children ?? defaultLabels[key] ?? key;

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-semibold rounded-full border tracking-wide uppercase font-mono ${sizeStyles[size]} ${colorClasses} ${className}`}
      {...props}
    >
      {isPulsing && (
        <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse shrink-0" />
      )}
      {label}
    </span>
  );
};

export default Badge;
