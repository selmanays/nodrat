/**
 * Minimal SVG sparkline — küme kartlarında canlı haber-hacmi mini-grafiği (Faz 4).
 * Veri: son 24s bucket-başına haber sayısı (my_clusters.spark). currentColor kullanır
 * → renk çağrı yerinden (text-* className). Tüm-sıfır/yetersiz veri → null.
 */
export function Sparkline({
  data,
  className,
  width = 60,
  height = 18,
}: {
  data: number[] | undefined;
  className?: string;
  width?: number;
  height?: number;
}) {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data);
  if (max <= 0) return null; // tüm-sıfır → grafik yok (kart "sakin" gösterir)

  const stepX = width / (data.length - 1);
  const pad = 1.5;
  const points = data
    .map((v, i) => {
      const x = i * stepX;
      const y = height - pad - (v / max) * (height - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-hidden="true"
      preserveAspectRatio="none"
    >
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
