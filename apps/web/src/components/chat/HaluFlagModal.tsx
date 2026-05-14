"use client";

import { useState } from "react";
import { Loader2, ThumbsDown } from "lucide-react";
import { toast } from "sonner";

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
import { Textarea } from "@/components/ui/textarea";
import { flagChatMessageHalu } from "@/lib/api";

/**
 * HaluFlagModal — halüsinasyon bildirimi formu.
 *
 * Açık tutulduğunda iki textarea:
 *  1. Neden (opsiyonel — 0-500 char) — sebep özet
 *  2. Doğru cevap (opsiyonel — 0-5000 char) — DPO chosen
 *
 * Submit sonrası: flagChatMessageHalu API'sini çağırır, parent'a feedback verir.
 */
export interface HaluFlagModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  messageId: string;
  onFlagged?: () => void;
}

export function HaluFlagModal({
  open,
  onOpenChange,
  messageId,
  onFlagged,
}: HaluFlagModalProps) {
  const [reason, setReason] = useState("");
  const [chosen, setChosen] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await flagChatMessageHalu(
        messageId,
        reason.trim() || null,
        chosen.trim() || null,
      );
      toast.success("Geri bildirim kaydedildi");
      onOpenChange(false);
      setReason("");
      setChosen("");
      onFlagged?.();
    } catch (e: unknown) {
      toast.error(
        e instanceof Error ? e.message : "Bildirim kaydedilemedi",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ThumbsDown className="size-4" />
            Halüsinasyon bildir
          </DialogTitle>
          <DialogDescription>
            Bu cevabın hatalı veya uydurma olduğunu mu düşünüyorsun? Bildirin
            modeli iyileştirmemize yardımcı olur. (DPO — Direct Preference
            Optimization training)
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="halu-reason">
              Sorun nedir? <span className="text-muted-foreground">(opsiyonel)</span>
            </Label>
            <Textarea
              id="halu-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value.slice(0, 500))}
              placeholder="Örn. Kaynakta belirtilmeyen bir tarih uydurmuş."
              rows={2}
              disabled={submitting}
            />
            <p className="text-right text-xs text-muted-foreground">
              {reason.length}/500
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="halu-chosen">
              Doğru cevap ne olmalıydı?{" "}
              <span className="text-muted-foreground">(opsiyonel)</span>
            </Label>
            <Textarea
              id="halu-chosen"
              value={chosen}
              onChange={(e) => setChosen(e.target.value.slice(0, 5000))}
              placeholder="Buraya doğru cevabı yazabilirsen DPO training için altın etiket olarak kullanırız."
              rows={4}
              disabled={submitting}
            />
            <p className="text-right text-xs text-muted-foreground">
              {chosen.length}/5000
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            Vazgeç
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting && <Loader2 className="mr-2 size-4 animate-spin" />}
            Bildir
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
