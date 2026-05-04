"use client"

import * as React from "react"
import {
  Area,
  AreaChart,
  CartesianGrid,
  XAxis,
  YAxis,
} from "recharts"

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { InfoTooltip } from "@/components/info-tooltip"

import type { ProviderSeries } from "@/lib/api"

export type ChartBucket = "hour" | "day" | "week"

export interface DashboardAreaChartCardProps {
  title: string
  unitLabel: string
  series: ProviderSeries[]
  bucket?: ChartBucket
  labelMap?: Record<string, string>
  /** Bu provider key foreground rengi ile vurgulanır (içerik üretim modeli). */
  highlightKey?: string
  hint?: React.ReactNode
  rangeOptions?: Array<{ value: string; label: string }>
  rangeValue?: string
  onRangeChange?: (value: string) => void
}

function tickFormatter(bucket: ChartBucket) {
  return (v: string) => {
    const d = new Date(v)
    if (bucket === "hour") {
      return d.toLocaleTimeString("tr-TR", {
        hour: "2-digit",
        minute: "2-digit",
      })
    }
    return d.toLocaleDateString("tr-TR", {
      day: "2-digit",
      month: "short",
    })
  }
}

function tooltipLabelFormatter(bucket: ChartBucket) {
  return (_label: unknown, payload: unknown) => {
    const arr = payload as Array<{ payload?: { hour?: string } }> | undefined
    const ts = arr?.[0]?.payload?.hour
    if (!ts) return ""
    const d = new Date(ts)
    if (bucket === "hour") {
      return d.toLocaleTimeString("tr-TR", {
        hour: "2-digit",
        minute: "2-digit",
      })
    }
    return d.toLocaleDateString("tr-TR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    })
  }
}

function colorForProvider(
  provider: string,
  idx: number,
  highlightKey?: string,
): string {
  if (highlightKey && provider === highlightKey) return "var(--foreground)"
  return `var(--chart-${(idx % 5) + 1})`
}

export function DashboardAreaChartCard({
  title,
  unitLabel,
  series,
  bucket = "hour",
  labelMap = {},
  highlightKey,
  hint,
  rangeOptions,
  rangeValue,
  onRangeChange,
}: DashboardAreaChartCardProps) {
  const merged = React.useMemo(() => {
    if (series.length === 0)
      return [] as Array<
        Record<string, number | string> & { hour: string; total: number }
      >
    const hourSet = new Set<string>()
    series.forEach((s) => s.buckets.forEach((b) => hourSet.add(b.hour)))
    const hours = Array.from(hourSet).sort()
    return hours.map((hour) => {
      const row: Record<string, number | string> = { hour }
      let total = 0
      for (const s of series) {
        const v = s.buckets.find((b) => b.hour === hour)?.count ?? 0
        row[s.provider] = v
        total += v
      }
      row.total = total
      return row as Record<string, number | string> & {
        hour: string
        total: number
      }
    })
  }, [series])

  const totalSum = merged.reduce((sum, r) => sum + (r.total as number), 0)

  const chartConfig = React.useMemo<ChartConfig>(() => {
    const cfg: ChartConfig = {}
    series.forEach((s, idx) => {
      cfg[s.provider] = {
        label: labelMap[s.provider] ?? s.provider,
        color: colorForProvider(s.provider, idx, highlightKey),
      }
    })
    return cfg
  }, [series, labelMap, highlightKey])

  return (
    <Card className="rounded-2xl pb-0 shadow-none ring-[var(--border)]">
      <CardHeader>
        <CardTitle className="line-clamp-1 text-base">{title}</CardTitle>
        <CardDescription className="line-clamp-1 flex items-center gap-1.5">
          <span className="truncate">
            {totalSum.toLocaleString("tr-TR")} {unitLabel}
          </span>
          {hint && <InfoTooltip content={hint} />}
        </CardDescription>
        {rangeOptions && rangeValue && onRangeChange && (
          <CardAction>
            <ToggleGroup
              type="single"
              value={rangeValue}
              onValueChange={(v) => v && onRangeChange(v)}
              variant="outline"
              size="sm"
            >
              {rangeOptions.map((opt) => (
                <ToggleGroupItem key={opt.value} value={opt.value}>
                  {opt.label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="px-0 pb-1">
        <ChartContainer config={chartConfig} className="h-64 w-full">
          <AreaChart
            data={merged}
            margin={{ top: 4, right: 0, left: 0, bottom: 0 }}
          >
            <defs>
              {series.map((s, idx) => {
                const c = colorForProvider(s.provider, idx, highlightKey)
                return (
                  <linearGradient
                    key={s.provider}
                    id={`fill-${s.provider}`}
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop offset="5%" stopColor={c} stopOpacity={0.4} />
                    <stop offset="95%" stopColor={c} stopOpacity={0.05} />
                  </linearGradient>
                )
              })}
            </defs>
            <CartesianGrid vertical={false} strokeDasharray="3 3" />
            <XAxis
              dataKey="hour"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              tickFormatter={tickFormatter(bucket)}
            />
            <YAxis
              hide
              domain={[0, (dataMax: number) => (dataMax > 0 ? dataMax : 1)]}
              allowDecimals={false}
            />
            <ChartTooltip
              cursor={false}
              content={
                <ChartTooltipContent
                  labelFormatter={tooltipLabelFormatter(bucket)}
                />
              }
            />
            {series.map((s, idx) => (
              <Area
                key={s.provider}
                dataKey={s.provider}
                type="monotone"
                stackId="1"
                stroke={colorForProvider(s.provider, idx, highlightKey)}
                strokeWidth={1}
                fill={`url(#fill-${s.provider})`}
              />
            ))}
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}

export function DashboardAreaChartCardSkeleton() {
  return (
    <Card className="rounded-2xl pb-0 shadow-none ring-[var(--border)]">
      <CardHeader>
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-24" />
        <CardAction>
          <Skeleton className="h-8 w-64 rounded-full" />
        </CardAction>
      </CardHeader>
      <CardContent className="px-0 pb-1">
        <Skeleton className="h-64 w-full rounded-none" />
      </CardContent>
    </Card>
  )
}
