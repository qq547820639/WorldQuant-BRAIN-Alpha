import { useCallback, useRef, useState, type FC } from "react";
import ConfirmDialog from "@/components/ConfirmDialog";
import type { ConfirmDialogProps } from "@/components/ConfirmDialog";

export interface ConfirmOptions {
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  variant?: "default" | "danger";
}

export interface UseConfirmReturn {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  ConfirmDialogComponent: FC;
}

export function useConfirm(): UseConfirmReturn {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolverRef = useRef<((value: boolean) => void) | null>(null);

  const confirm = useCallback((opts: ConfirmOptions): Promise<boolean> => {
    setOptions(opts);
    setOpen(true);

    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
    });
  }, []);

  const handleConfirm = useCallback(() => {
    setOpen(false);
    if (resolverRef.current) {
      resolverRef.current(true);
      resolverRef.current = null;
    }
  }, []);

  const handleCancel = useCallback(() => {
    setOpen(false);
    if (resolverRef.current) {
      resolverRef.current(false);
      resolverRef.current = null;
    }
  }, []);

  const ConfirmDialogComponent: FC = () => {
    if (!options) return null;

    return (
      <ConfirmDialog
        open={open}
        title={options.title}
        description={options.description}
        confirmText={options.confirmText}
        cancelText={options.cancelText}
        variant={options.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    );
  };

  return { confirm, ConfirmDialogComponent };
}

export default useConfirm;
