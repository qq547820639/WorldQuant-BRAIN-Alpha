/**
 * LazyImage — 懒加载图片组件
 * 使用 IntersectionObserver 实现懒加载，支持骨架屏和淡入效果
 */
import {
  memo,
  useState,
  useCallback,
  useEffect,
  type ImgHTMLAttributes,
  type ReactNode,
} from 'react';
import Skeleton from '../Skeleton';
import { useInView } from '../../hooks/useIntersectionObserver';

export interface LazyImageProps extends Omit<
  ImgHTMLAttributes<HTMLImageElement>,
  'onLoad' | 'onError'
> {
  src: string;
  alt: string;
  placeholder?: ReactNode;
  fallbackSrc?: string;
  fadeIn?: boolean;
  fadeDuration?: number;
  rootMargin?: string;
  threshold?: number;
  onLoad?: (img: HTMLImageElement) => void;
  onError?: (error: Event) => void;
  className?: string;
  wrapperClassName?: string;
}

export default memo(function LazyImage({
  src,
  alt,
  placeholder,
  fallbackSrc,
  fadeIn = true,
  fadeDuration = 300,
  rootMargin = '200px',
  threshold = 0.01,
  onLoad,
  onError,
  className = '',
  wrapperClassName = '',
  style,
  ...imgProps
}: LazyImageProps) {
  const [isLoaded, setIsLoaded] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [shouldLoad, setShouldLoad] = useState(false);

  const { ref, isInView } = useInView<HTMLDivElement>({
    rootMargin,
    threshold,
    triggerOnce: true,
    initialInView: false,
  });

  const handleLoad = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement>) => {
      setIsLoaded(true);
      onLoad?.(e.currentTarget);
    },
    [onLoad]
  );

  const handleError = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement>) => {
      setHasError(true);
      onError?.(e.nativeEvent);
    },
    [onError]
  );

  useEffect(() => {
    if (isInView && !shouldLoad) {
      setShouldLoad(true);
    }
  }, [isInView, shouldLoad]);

  const currentSrc = hasError && fallbackSrc ? fallbackSrc : src;

  return (
    <div ref={ref} className={`relative ${wrapperClassName}`} style={style}>
      {!isLoaded && !hasError && (
        <div className="absolute inset-0">
          {placeholder || <Skeleton variant="card" className="w-full h-full" />}
        </div>
      )}

      {hasError && fallbackSrc && (
        <img
          src={fallbackSrc}
          alt={alt}
          className={`${className}`}
          style={{
            opacity: isLoaded ? 1 : 0,
            transition: fadeIn ? `opacity ${fadeDuration}ms ease-in-out` : 'none',
          }}
          onLoad={handleLoad}
          {...imgProps}
        />
      )}

      {shouldLoad && (!hasError || !fallbackSrc) && (
        <img
          src={currentSrc}
          alt={alt}
          className={`${className}`}
          style={{
            opacity: isLoaded ? 1 : 0,
            transition: fadeIn ? `opacity ${fadeDuration}ms ease-in-out` : 'none',
            display: 'block',
          }}
          onLoad={handleLoad}
          onError={handleError}
          {...imgProps}
        />
      )}

      {hasError && !fallbackSrc && (
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{ background: 'var(--color-surface-subtle)' }}
        >
          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            style={{ color: 'var(--color-text-dim)' }}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
        </div>
      )}
    </div>
  );
});
