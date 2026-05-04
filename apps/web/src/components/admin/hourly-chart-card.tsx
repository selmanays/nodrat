"use client"

import * as React from "react"
import { Area, AreaChart } from "recharts"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  CardAction,
} from "@/components/ui/card"
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"

import type { HourlyBucket } from "@/lib/api"

type ChartColor = "chart-1" | "chart-2" | "chart-3" | "chart-4" | "chart-5"

export interface HourlyChartCardProps {
  title: string
  description: string
  data: HourlyBucket[]
  color?: ChartColor
}

function trendBadge(data: HourlyBucket[]): {
  label: string
  variant: "secondary" | "outline" | "destructive"
} {
  if (data.length < 2) return { label: "—", variant: "outline" }
  const last = data[data.length - 1]?.count ?? 0
  const prev = data[data.length - 2]?.count ?? 0
  if (prev === 0 && last === 0) return { label: "—", variant: "outline" }
  if (prev === 0) return { label: `+${last}`, variant: "secondary" }
  const delta = ((last - prev) / prev) * 100
  const sign = delta >= 0 ? "+" : ""
  const variant: "secondary" | "destructive" =
    delta < 0 ? "destructive" : "secondary"
  return { label: `${sign}${delta.toFixed(0)}% vs ön. saat`, variant }
}

export function HourlyChartCard({
  title,
  description,
  data,
  color = "chart-1",
}: HourlyChartCardProps) {
  const total = data.reduce((sum, d) => sum + d.count, 0)
  const trend = trendBadge(data)

  const chartConfig = {
    count: {
      label: title,
      color: `var(--${color})`,
    },
  } satisfies ChartConfig

  return (
    <Card className="rounded-2xl pb-0 shadow-none">
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>
          {description} · toplam {total.toLocaleString("tr-TR")}
        </CardDescription>
        <CardAction>
          <Badge variant={trend.variant}>{trend.label}</Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="px-0">
        <ChartContainer config={chartConfig} className="h-32 w-full">
          <AreaChart data={data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
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
            <defs>
              <linearGradient id={`fill-${color}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={`var(--${color})`} stopOpacity={0.4} />
                <stop offset="95%" stopColor={`var(--${color})`} stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <Area
              dataKey="count"
              type="monotone"
              stroke={`var(--${color})`}
              strokeWidth={2}
              fill={`url(#fill-${color})`}
            />
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
