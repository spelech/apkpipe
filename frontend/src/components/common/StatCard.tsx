import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, LucideIcon } from 'lucide-react';

export interface StatCardProps {
  title: string;
  value: string | number | React.ReactNode;
  subtitle?: string | React.ReactNode;
  icon?: LucideIcon | React.ComponentType<{ className?: string }> | React.ReactNode;
  iconColor?: string;
  iconBg?: string;
  to?: string;
  href?: string;
  linkText?: string;
  trend?: {
    value: string;
    isPositive?: boolean;
  };
  className?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  icon: IconOrElement,
  iconColor = 'text-indigo-400',
  iconBg = 'bg-indigo-500/10 border-indigo-500/20',
  to,
  href,
  linkText = 'View Details',
  trend,
  className = '',
}) => {
  const renderIcon = () => {
    if (!IconOrElement) return null;
    if (React.isValidElement(IconOrElement)) {
      return IconOrElement;
    }
    const IconComponent = IconOrElement as React.ComponentType<{ className?: string }>;
    return <IconComponent className={`w-5 h-5 ${iconColor}`} />;
  };

  const renderLink = () => {
    if (to) {
      return (
        <Link
          to={to}
          className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-indigo-400 hover:text-indigo-300 transition group"
        >
          <span>{linkText}</span>
          <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
        </Link>
      );
    }
    if (href) {
      return (
        <a
          href={href}
          className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-indigo-400 hover:text-indigo-300 transition group"
        >
          <span>{linkText}</span>
          <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
        </a>
      );
    }
    return null;
  };

  return (
    <div
      className={`glass-panel p-5 rounded-2xl border border-slate-800/80 relative overflow-hidden transition-all duration-200 hover:-translate-y-0.5 hover:border-slate-700/80 hover:shadow-lg hover:shadow-black/30 flex flex-col justify-between ${className}`}
    >
      <div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            {title}
          </span>
          {IconOrElement && (
            <div className={`p-2.5 rounded-xl border ${iconBg} shrink-0`}>
              {renderIcon()}
            </div>
          )}
        </div>

        <div className="mt-4 flex items-baseline gap-2 flex-wrap">
          <div className="text-3xl font-extrabold text-white tracking-tight">
            {value}
          </div>
          {subtitle && (
            <div className="text-xs text-slate-400 font-medium">
              {subtitle}
            </div>
          )}
        </div>

        {trend && (
          <div
            className={`mt-1 text-xs font-medium ${
              trend.isPositive ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {trend.value}
          </div>
        )}
      </div>

      {renderLink()}
    </div>
  );
};

export default StatCard;
