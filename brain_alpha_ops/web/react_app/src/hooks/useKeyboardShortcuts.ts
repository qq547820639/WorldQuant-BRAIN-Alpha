import { useEffect, useCallback, useRef } from 'react';

export interface Shortcut {
  key: string;
  description: string;
  category: string;
  action: () => void;
}

export interface KeyboardShortcutsOptions {
  onRefresh?: () => void;
  onNavigateToDashboard?: () => void;
  onNavigateToConfig?: () => void;
  onSearchFocus?: () => void;
  onShowHelp?: () => void;
  onEscape?: () => void;
}

const SEQUENCE_TIMEOUT_MS = 1500;

function isEditableElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  ) {
    return true;
  }
  if (target.isContentEditable) return true;
  const tagName = target.tagName.toLowerCase();
  if (tagName === 'input' || tagName === 'textarea' || tagName === 'select') {
    return true;
  }
  return false;
}

function focusFirstSearchInput(): boolean {
  const searchInput = document.querySelector<HTMLInputElement>(
    'input[type="search"], input[placeholder*="搜索"], input[placeholder*="search"], input[aria-label*="搜索"], input[aria-label*="search"]'
  );
  if (searchInput) {
    searchInput.focus();
    return true;
  }
  return false;
}

export function useKeyboardShortcuts(options: KeyboardShortcutsOptions) {
  const sequencePrefixRef = useRef<string | null>(null);
  const sequenceTimerRef = useRef<number | null>(null);

  const clearSequenceTimer = useCallback(() => {
    if (sequenceTimerRef.current !== null) {
      window.clearTimeout(sequenceTimerRef.current);
      sequenceTimerRef.current = null;
    }
  }, []);

  const resetSequence = useCallback(() => {
    clearSequenceTimer();
    sequencePrefixRef.current = null;
  }, [clearSequenceTimer]);

  const startSequenceTimer = useCallback(() => {
    clearSequenceTimer();
    sequenceTimerRef.current = window.setTimeout(() => {
      sequencePrefixRef.current = null;
      sequenceTimerRef.current = null;
    }, SEQUENCE_TIMEOUT_MS);
  }, [clearSequenceTimer]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (isEditableElement(e.target)) return;

      const key = e.key.toLowerCase();

      if (key === 'escape') {
        e.preventDefault();
        resetSequence();
        options.onEscape?.();
        return;
      }

      if (key === '?' || (e.shiftKey && key === '/')) {
        e.preventDefault();
        resetSequence();
        options.onShowHelp?.();
        return;
      }

      if (sequencePrefixRef.current === 'g') {
        if (key === 'd') {
          e.preventDefault();
          resetSequence();
          options.onNavigateToDashboard?.();
          return;
        }
        if (key === 'c') {
          e.preventDefault();
          resetSequence();
          options.onNavigateToConfig?.();
          return;
        }
        resetSequence();
      }

      if (key === 'g') {
        e.preventDefault();
        sequencePrefixRef.current = 'g';
        startSequenceTimer();
        return;
      }

      if (key === '/') {
        e.preventDefault();
        resetSequence();
        const handled = options.onSearchFocus !== undefined ? false : focusFirstSearchInput();
        if (!handled) {
          options.onSearchFocus?.();
        }
        return;
      }

      if (key === 'r' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        resetSequence();
        options.onRefresh?.();
        return;
      }

      resetSequence();
    },
    [options, resetSequence, startSequenceTimer]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      clearSequenceTimer();
    };
  }, [handleKeyDown, clearSequenceTimer]);
}

export const SHORTCUTS_LIST: Array<{
  keys: string[];
  description: string;
  category: string;
}> = [
  {
    keys: ['/'],
    description: '聚焦搜索框',
    category: '导航',
  },
  {
    keys: ['g', 'd'],
    description: '跳转到运行总览',
    category: '导航',
  },
  {
    keys: ['g', 'c'],
    description: '跳转到系统配置',
    category: '导航',
  },
  {
    keys: ['r'],
    description: '刷新数据',
    category: '操作',
  },
  {
    keys: ['?'],
    description: '显示快捷键帮助',
    category: '帮助',
  },
  {
    keys: ['Esc'],
    description: '关闭对话框 / 取消操作',
    category: '操作',
  },
];
