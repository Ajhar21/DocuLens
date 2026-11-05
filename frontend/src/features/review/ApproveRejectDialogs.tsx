import { useState } from "react";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";

interface RejectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reason: string) => Promise<void>;
  isSubmitting: boolean;
}

export function RejectDialog({
  open,
  onOpenChange,
  onConfirm,
  isSubmitting,
}: RejectDialogProps) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    const trimmed = reason.trim();
    if (!trimmed) {
      setError("A rejection reason is required.");
      return;
    }
    setError(null);
    await onConfirm(trimmed);
    setReason("");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <DialogTitle>Reject Document</DialogTitle>
          </div>
          <DialogDescription className="text-xs">
            Rejecting this invoice reopens it for re-review and corrections. A clear reason must be provided for the audit log.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-2">
          <Label htmlFor="reject-reason" className="text-xs font-semibold">
            Rejection Reason (Required)
          </Label>
          <textarea
            id="reject-reason"
            rows={3}
            placeholder="Explain why this invoice is being rejected (e.g. invalid tax calculation, missing supplier TIN)..."
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              if (error) setError(null);
            }}
            disabled={isSubmitting}
            className="flex w-full rounded-md border border-input bg-background p-2 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            size="sm"
            onClick={handleConfirm}
            disabled={!reason.trim() || isSubmitting}
          >
            {isSubmitting ? "Rejecting…" : "Confirm Rejection"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface ApproveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (notes?: string) => Promise<void>;
  isSubmitting: boolean;
}

export function ApproveDialog({
  open,
  onOpenChange,
  onConfirm,
  isSubmitting,
}: ApproveDialogProps) {
  const [notes, setNotes] = useState("");

  const handleConfirm = async () => {
    await onConfirm(notes.trim() || undefined);
    setNotes("");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="h-5 w-5" />
            <DialogTitle>Approve Invoice</DialogTitle>
          </div>
          <DialogDescription className="text-xs">
            Approving this document locks the header fields against further edits and marks the invoice as verified.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-2">
          <Label htmlFor="approve-notes" className="text-xs font-semibold">
            Approval Notes (Optional)
          </Label>
          <textarea
            id="approve-notes"
            rows={2}
            placeholder="Optional verification notes or sign-off remarks..."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={isSubmitting}
            className="flex w-full rounded-md border border-input bg-background p-2 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
          />
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={handleConfirm}
            disabled={isSubmitting}
            className="bg-emerald-600 hover:bg-emerald-700 text-white"
          >
            {isSubmitting ? "Approving…" : "Approve & Lock"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

