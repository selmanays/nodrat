"use client"

import * as React from "react"
import {
  Area,
  AreaChart,
  CartesianGrid,
  XAxis,
  YAxis,
} from "recharts"

import { Badge } from "@/components/ui/badge"
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
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import { InfoTooltip } from "@/components/info-tooltip"

import type { ProviderSeries } from "@/lib/api"

export interface DashboardAreaChartCardProps {
  title: string
  unitLabel: string
  series: ProviderSeries[]
  labelMap?: Record<string, string>
  hint?: React.ReactNode
}

function trendBadge(merged: { hour: string; total: number }[]): {
  label: string
  variant: "secondary" | "outline" | "destructive"
} {
  if (merged.length < 2) return { label: "—", variant: "outline" }
  const last = merged[merged.length - 1]?.total ?? 0
  const prev = merged[merged.length - 2]?.total ?? 0
  if (prev === 0 && last === 0) return { label: "—", variant: "outline" }
  if (prev === 0) return { label: `+${last}`, variant: "secondary" }
  const delta = ((last - prev) / prev) * 100
  const sign = delta >= 0 ? "+" : ""
  const variant: "secondary" | "destructive" =
    delta < 0 ? "destructive" : "secondary"
  return { label: `${sign}${delta.toFixed(0)}% vs ön. saat`, variant }
}

export function DashboardAreaChartCard({
  title,
  unitLabel,
  series,
  labelMap = {},
  hint,
}: DashboardAreaChartCardProps) {
  // hour -> { hour, [provider]: count } merged data + total per row
  const merged = React.useMemo(() => {
    if (series.length === 0) return [] as Array<Record<string, number | string> & { hour: string; total: number }>
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
      return row as Record<string, number | string> & { hour: string; total: number }
    })
  }, [series])

  const totalSum = merged.reduce((sum, r) => sum + (r.total as number), 0)
  const trend = trendBadge(merged)

  // Color cycle from --chart-1..5
  const chartConfig = React.useMemo<ChartConfig>(() => {
    const cfg: ChartConfig = {}
    series.forEach((s, idx) => {
      cfg[s.provider] = {
        label: labelMap[s.provider] ?? s.provider,
        color: `var(--chart-${(idx % 5) + 1})`,
      }
    })
    return cfg
  }, [series, labelMap])

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
        <CardAction>
          <Badge variant={trend.variant}>{trend.label}</Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="px-2 pb-2">
        <ChartContainer config={chartConfig} className="h-64 w-full">
          <AreaChart
            data={merged}
            margin={{ top: 4, right: 4, left: 4, bottom: 0 }}
          >
            <defs>
              {series.map((s, idx) => (
                <linearGradient
                  key={s.provider}
                  id={`fill-${s.provider}`}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="5%"
                    stopColor={`var(--chart-${(idx % 5) + 1})`}
                    stopOpacity={0.4}
                  />
                  <stop
                    offset="95%"
                    stopColor={`var(--chart-${(idx % 5) + 1})`}
                    stopOpacity={0.05}
                  />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid vertical={false} strokeDasharray="3 3" />
            <XAxis
              dataKey="hour"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              tickFormatter={(v: string) =>
                new Date(v).toLocaleTimeString("tr-TR", {
                  hour: "2-digit",
                  minute: "2-digit",
                })
              }
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
                  labelFormatter={(_label, payload) => {
                    const ts = payload?.[0]?.payload?.hour as string | undefined
                    if (!ts) return ""
                    return new Date(ts).toLocaleTimeString("tr-TR", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  }}
                />
              }
            />
            <ChartLegend content={<ChartLegendContent />} />
            {series.map((s, idx) => (
              <Area
                key={s.provider}
                dataKey={s.provider}
                type="monotone"
                stackId="1"
                stroke={`var(--chart-${(idx % 5) + 1})`}
                strokeWidth={2}
                fill={`url(#fill-${s.provider})`}
              />
            ))}
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
