/**
 * TrendSparkline — pencere içi saatlik haber sayısı mini grafiği (Faz 1, #1500).
 *
 * Eksensiz/gridsiz küçük Recharts AreaChart (tablo hücresi için sabit boyut).
 * Veri = backend `sparkline: {bucket_start, article_count}[]`.
 */

"use client";

import { Area, AreaChart } from "recharts";

import type { TrendSparkPoint } from "@/lib/api";

export function TrendSparkline({
  data,
  width = 120,
  height = 32,
}: {
  data: TrendSparkPoint[];
  width?: number;
  height?: number;
}) {
  if (!data || data.length === 0) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  return (
    <AreaChart
      width={width}
      height={height}
      data={data}
      margin={{ top: 2, right: 2, bottom: 2, left: 2 }}
    >
      <defs>
        <linearGradient id="trendSpark" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.5} />
          <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0.05} />
        </linearGradient>
      </defs>
      <Area
        type="monotone"
        dataKey="article_count"
        stroke="var(--chart-1)"
        strokeWidth={1.5}
        fill="url(#trendSpark)"
        isAnimationActive={false}
        dot={false}
      />
    </AreaChart>
  );
}
