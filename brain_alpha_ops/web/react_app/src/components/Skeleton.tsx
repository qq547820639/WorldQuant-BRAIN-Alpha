/**
 * Skeleton — loading skeleton component for better UX.
 * Shows animated placeholder content while data is loading.
 */
interface SkeletonProps {
  variant?: 'card' | 'text' | 'avatar' | 'table-row';
  className?: string;
}

const skeletonStyle = { backgroundColor: "var(--color-border-subtle)" };

export default function Skeleton({ variant = 'text', className = '' }: SkeletonProps) {
  const baseClass = 'animate-pulse';

  switch (variant) {
    case 'card':
      return (
        <div className={`${baseClass} rounded-lg p-4 ${className}`} style={skeletonStyle}>
          <div className="flex justify-between items-center mb-3">
            <div className={`${baseClass} h-5 w-28 rounded`} style={skeletonStyle} />
            <div className={`${baseClass} h-6 w-16 rounded-full`} style={skeletonStyle} />
          </div>
          <div className="space-y-2">
            <div className={`${baseClass} h-3 w-full rounded`} style={skeletonStyle} />
            <div className={`${baseClass} h-3 w-4/5 rounded`} style={skeletonStyle} />
          </div>
          <div className="flex gap-2 mt-4">
            <div className={`${baseClass} h-8 w-20 rounded-md`} style={skeletonStyle} />
            <div className={`${baseClass} h-8 w-20 rounded-md`} style={skeletonStyle} />
          </div>
        </div>
      );

    case 'text':
      return <div className={`${baseClass} h-3 w-full rounded ${className}`} style={skeletonStyle} />;

    case 'avatar':
      return <div className={`${baseClass} h-10 w-10 rounded-full ${className}`} style={skeletonStyle} />;

    case 'table-row':
      return (
        <div className={`flex gap-4 items-center ${className}`}>
          <div className={`${baseClass} h-8 w-8 rounded-full`} style={skeletonStyle} />
          <div className={`${baseClass} h-3 w-24 rounded`} style={skeletonStyle} />
          <div className={`${baseClass} h-3 w-32 rounded`} style={skeletonStyle} />
          <div className={`${baseClass} h-3 w-16 rounded`} style={skeletonStyle} />
        </div>
      );

    default:
      return <div className={`${baseClass} h-3 w-full rounded ${className}`} style={skeletonStyle} />;
  }
}
