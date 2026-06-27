/**
 * VirtualList — 虚拟滚动组件
 * 基于 @tanstack/react-virtual 实现，支持固定/动态高度、横向/纵向滚动
 */
import { memo, useRef, forwardRef, useImperativeHandle, type ReactNode } from 'react';
import { useVirtualizer, useWindowVirtualizer, type Virtualizer } from '@tanstack/react-virtual';

type VirtualListDirection = 'vertical' | 'horizontal';

export interface VirtualListProps<T> {
  items: T[];
  renderItem: (item: T, index: number) => ReactNode;
  itemSize?: number;
  estimateSize?: (index: number) => number;
  direction?: VirtualListDirection;
  overscan?: number;
  className?: string;
  containerClassName?: string;
  useWindowScroll?: boolean;
  getItemKey?: (index: number, item: T) => string | number;
  onScroll?: (offset: number) => void;
  scrollMargin?: number;
}

export interface VirtualListHandle {
  scrollToIndex: (index: number, align?: 'start' | 'center' | 'end' | 'auto') => void;
  scrollToOffset: (offset: number, align?: 'start' | 'center' | 'end' | 'auto') => void;
  getVirtualizer: () => Virtualizer<Element, Element> | null;
}

const VirtualListInner = forwardRef(function VirtualListInner<T>(
  {
    items,
    renderItem,
    itemSize,
    estimateSize,
    direction = 'vertical',
    overscan = 5,
    className = '',
    containerClassName = '',
    useWindowScroll = false,
    getItemKey,
    onScroll,
    scrollMargin = 0,
  }: VirtualListProps<T>,
  ref: React.Ref<VirtualListHandle>
) {
  const parentRef = useRef<HTMLDivElement>(null);
  const isHorizontal = direction === 'horizontal';

  const virtualizerOptions = {
    count: items.length,
    estimateSize: estimateSize || (itemSize ? () => itemSize : undefined),
    overscan,
    horizontal: isHorizontal,
    scrollMargin,
    getItemKey: getItemKey ? (index: number) => getItemKey(index, items[index]) : undefined,
    onChange: (instance: { scrollOffset?: number }) => {
      // [REFACTORED] virtual-core uses scrollOffset, not scrollLeft/scrollTop.
      // 结构类型同时兼容 useWindowVirtualizer (Virtualizer<Window, Element>)
      // 与 useVirtualizer (Virtualizer<Element, Element>) 的 onChange 签名。
      onScroll?.(instance.scrollOffset ?? 0);
    },
  };

  const rowVirtualizer = useWindowScroll
    ? useWindowVirtualizer({
        ...virtualizerOptions,
        // [REFACTORED] useWindowVirtualizer uses 'getScrollElement', not 'scrollElement'
        getScrollElement: () => typeof window !== 'undefined' ? window : null,
      })
    : useVirtualizer({
        ...virtualizerOptions,
        getScrollElement: () => parentRef.current,
      });

  useImperativeHandle(ref, () => ({
    scrollToIndex: (index: number, align: 'start' | 'center' | 'end' | 'auto' = 'start') => {
      rowVirtualizer.scrollToIndex(index, { align });
    },
    scrollToOffset: (offset: number, align: 'start' | 'center' | 'end' | 'auto' = 'start') => {
      rowVirtualizer.scrollToOffset(offset, { align });
    },
    getVirtualizer: () => rowVirtualizer as unknown as Virtualizer<Element, Element>,
  }));

  const virtualItems = rowVirtualizer.getVirtualItems();
  const totalSize = rowVirtualizer.getTotalSize();

  if (useWindowScroll) {
    return (
      <div
        className={className}
        style={{
          position: 'relative',
          width: isHorizontal ? totalSize : '100%',
          height: isHorizontal ? '100%' : totalSize,
        }}
      >
        {virtualItems.map((virtualItem) => (
          <div
            key={virtualItem.key}
            ref={rowVirtualizer.measureElement}
            data-index={virtualItem.index}
            style={{
              position: 'absolute',
              top: isHorizontal ? 0 : virtualItem.start,
              left: isHorizontal ? virtualItem.start : 0,
              width: isHorizontal ? virtualItem.size : '100%',
              height: isHorizontal ? '100%' : virtualItem.size,
            }}
          >
            {renderItem(items[virtualItem.index], virtualItem.index)}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      className={`${containerClassName}`}
      style={{
        overflow: isHorizontal ? 'auto hidden' : 'hidden auto',
        contain: 'strict',
        width: '100%',
        height: '100%',
      }}
    >
      <div
        className={className}
        style={{
          position: 'relative',
          width: isHorizontal ? totalSize : '100%',
          height: isHorizontal ? '100%' : totalSize,
        }}
      >
        {virtualItems.map((virtualItem) => (
          <div
            key={virtualItem.key}
            ref={rowVirtualizer.measureElement}
            data-index={virtualItem.index}
            style={{
              position: 'absolute',
              top: isHorizontal ? 0 : virtualItem.start,
              left: isHorizontal ? virtualItem.start : 0,
              width: isHorizontal ? virtualItem.size : '100%',
              height: isHorizontal ? '100%' : virtualItem.size,
            }}
          >
            {renderItem(items[virtualItem.index], virtualItem.index)}
          </div>
        ))}
      </div>
    </div>
  );
}) as <T>(
  props: VirtualListProps<T> & { ref?: React.Ref<VirtualListHandle> }
) => React.ReactElement;

export default memo(VirtualListInner) as typeof VirtualListInner;
