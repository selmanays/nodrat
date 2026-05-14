"use client";

import { Check, Copy, ThumbsDown } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { HaluFlagModal } from "./HaluFlagModal";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { recordChatMessageAction } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * MessageActions — assistant mesajının altında küçük toolbar.
 *
 * Şu an: Copy + Halu Flag. (Edit — gelecek sprint.)
 */
export interface MessageActionsProps {
  messageId: string;
  content: string;
  alreadyFlagged?: boolean;
  alreadyAction?: string | null;
  className?: string;
}

export function MessageActions({
  messageId,
  content,
  alreadyFlagged = false,
  alreadyAction = null,
  className,
}: MessageActionsProps) {
  const [copied, setCopied] = useState(false);
  const [flagged, setFlagged] = useState(alreadyFlagged);
  const [actionState, setActionState] = useState<string | null>(alreadyAction);
  const [haluOpen, setHaluOpen] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      // Best-effort action kaydı (sessizce)
      recordChatMessageAction(messageId, "copied").catch(() => undefined);
      setActionState("copied");
      setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error("Kopyalama başarısız");
    }
  };

  return (
    <TooltipProvider delayDuration={400}>
      <div className={cn("flex items-center gap-1", className)}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-7 text-muted-foreground hover:text-foreground"
              onClick={handleCopy}
            >
              {copied ? (
                <Check className="size-3.5 text-emerald-500" />
              ) : (
                <Copy className="size-3.5" />
              )}
              <span className="sr-only">Kopyala</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            {actionState === "copied" ? "Kopyalandı" : "Kopyala"}
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                "size-7 text-muted-foreground hover:text-foreground",
                flagged && "text-rose-500 hover:text-rose-500",
              )}
              onClick={() => setHaluOpen(true)}
              disabled={flagged}
            >
              <ThumbsDown className="size-3.5" />
              <span className="sr-only">Halüsinasyon bildir</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            {flagged ? "Bildirildi" : "Halüsinasyon bildir"}
          </TooltipContent>
        </Tooltip>

        <HaluFlagModal
          open={haluOpen}
          onOpenChange={setHaluOpen}
          messageId={messageId}
          onFlagged={() => setFlagged(true)}
        />
      </div>
    </TooltipProvider>
  );
}
