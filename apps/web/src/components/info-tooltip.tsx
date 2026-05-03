"use client"

import * as React from "react"

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
          {children ?? (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              className="size-3.5"
            >
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4M12 8h.01" />
            </svg>
          )}
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
