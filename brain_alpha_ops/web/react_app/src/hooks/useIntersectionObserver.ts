/**
 * useIntersectionObserver - 交叉观察器 hook
 * 观察元素是否进入视口，用于懒加载、无限滚动等场景
 */
import { useState, useEffect, useRef, useCallback } from 'react';

interface UseIntersectionObserverOptions {
  root?: Element | null;
  rootMargin?: string;
  threshold?: number | number[];
  triggerOnce?: boolean;
}

interface UseIntersectionObserverResult<T extends Element = Element> {
  ref: React.RefCallback<T>;
  entry: IntersectionObserverEntry | null;
  isIntersecting: boolean;
}

export function useIntersectionObserver<T extends Element = Element>(
  options: UseIntersectionObserverOptions = {}
): UseIntersectionObserverResult<T> {
  const { root = null, rootMargin = '0px', threshold = 0, triggerOnce = false } = options;
  const [entry, setEntry] = useState<IntersectionObserverEntry | null>(null);
  const [isIntersecting, setIsIntersecting] = useState(false);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const elementRef = useRef<T | null>(null);
  const triggeredRef = useRef(false);

  const ref = useCallback(
    (node: T | null) => {
      if (observerRef.current) {
        observerRef.current.disconnect();
        observerRef.current = null;
      }

      elementRef.current = node;
      triggeredRef.current = false;

      if (node && typeof IntersectionObserver !== 'undefined') {
        observerRef.current = new IntersectionObserver(
          (entries) => {
            const [currentEntry] = entries;
            setEntry(currentEntry);
            setIsIntersecting(currentEntry.isIntersecting);

            if (triggerOnce && currentEntry.isIntersecting) {
              triggeredRef.current = true;
              observerRef.current?.disconnect();
              observerRef.current = null;
            }
          },
          { root, rootMargin, threshold }
        );
        observerRef.current.observe(node);
      }
    },
    [root, rootMargin, threshold, triggerOnce]
  );

  useEffect(() => {
    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
        observerRef.current = null;
      }
    };
  }, []);

  return { ref, entry, isIntersecting };
}

/**
 * useInView - 简化版，用于判断元素是否在视口中
 * 只返回 isInView 和 ref，更简洁的 API
 */
interface UseInViewOptions {
  root?: Element | null;
  rootMargin?: string;
  threshold?: number | number[];
  triggerOnce?: boolean;
  initialInView?: boolean;
}

interface UseInViewResult<T extends Element = Element> {
  ref: React.RefCallback<T>;
  isInView: boolean;
  entry: IntersectionObserverEntry | null;
}

export function useInView<T extends Element = Element>(
  options: UseInViewOptions = {}
): UseInViewResult<T> {
  const { initialInView = false, ...observerOptions } = options;
  const { ref, entry, isIntersecting } = useIntersectionObserver<T>(observerOptions);

  const isInView = entry ? isIntersecting : initialInView;

  return { ref, isInView, entry };
}
