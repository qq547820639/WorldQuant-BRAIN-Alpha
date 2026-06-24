/**
 * Skeleton — loading skeleton component for better UX.
 * Shows animated placeholder content while data is loading.
 */
interface SkeletonProps {
  variant?: 'card' | 'text' | 'avatar' | 'table-row';
  className?: string;
}

export default function Skeleton({ variant = 'text', className = '' }: SkeletonProps) {
  const baseClass = 'animate-pulse bg-gray-200';

  switch (variant) {
    case 'card':
      return (
        <div className={`${baseClass} rounded-lg p-4 ${className}`}>
          <div className="flex justify-between items-center mb-3">
            <div className={`${baseClass} h-5 w-28 rounded`} />
            <div className={`${baseClass} h-6 w-16 rounded-full`} />
          </div>
          <div className="space-y-2">
            <div className={`${baseClass} h-3 w-full rounded`} />
            <div className={`${baseClass} h-3 w-4/5 rounded`} />
          </div>
          <div className="flex gap-2 mt-4">
            <div className={`${baseClass} h-8 w-20 rounded-md`} />
            <div className={`${baseClass} h-8 w-20 rounded-md`} />
          </div>
        </div>
      );

    case 'text':
      return <div className={`${baseClass} h-3 w-full rounded ${className}`} />;

    case 'avatar':
      return <div className={`${baseClass} h-10 w-10 rounded-full ${className}`} />;

    case 'table-row':
      return (
        <div className={`flex gap-4 items-center ${className}`}>
          <div className={`${baseClass} h-8 w-8 rounded-full`} />
          <div className={`${baseClass} h-3 w-24 rounded`} />
          <div className={`${baseClass} h-3 w-32 rounded`} />
          <div className={`${baseClass} h-3 w-16 rounded`} />
        </div>
      );

    default:
      return <div className={`${baseClass} h-3 w-full rounded ${className}`} />;
  }
}
