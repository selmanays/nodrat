"use client"

import * as React from "react"
import { Info } from "lucide-react"

import { cn } from "@/lib/utils"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

export function InfoTooltip({
  children,
  content,
  className,
}: {
  children?: React.ReactNode
  content: React.ReactNode
  className?: string
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-flex cursor-help items-center text-muted-foreground hover:text-foreground",
            className,
          )}
        >
          {children ?? <Info className="size-3.5" />}
        </span>
      </TooltipTrigger>
      <TooltipContent>{content}</TooltipContent>
    </Tooltip>
  )
}

export function Term({
  label,
  description,
  hint,
}: {
  label: string
  description?: React.ReactNode
  hint?: React.ReactNode
}) {
  const content = description ?? hint
  return (
    <span className="inline-flex items-center gap-1">
      <span>{label}</span>
      {content !== undefined && <InfoTooltip content={content} />}
    </span>
  )
}
