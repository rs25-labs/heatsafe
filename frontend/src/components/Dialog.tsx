import { useEffect, useRef, type ReactNode } from "react";
import { useT } from "../i18n";

interface Props {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

/** A modal panel for secondary details, so they don't crowd the main screen. */
export default function Dialog({ title, open, onClose, children }: Props) {
  const t = useT();
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => { if (e.target === ref.current) onClose(); }}
      aria-labelledby="dialog-title"
      className="m-auto w-[min(640px,calc(100vw-32px))] rounded-lg border border-rule p-0 text-ink backdrop:bg-ink/40"
    >
      <div className="flex items-center justify-between border-b border-rule px-5 py-3">
        <h2 id="dialog-title" className="text-base font-bold">{title}</h2>
        <button type="button" onClick={onClose} className="h-9 rounded-md px-3 text-sm text-accent underline">
          {t("dialog.close")}
        </button>
      </div>
      <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
    </dialog>
  );
}
