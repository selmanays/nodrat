"use client";

/**
 * VPS Disk panel — host disk + Docker breakdown + güvenli build cache cleanup
 * (#570). shadcn preset b1VlIttI uyumlu (`mcp__Shadcn_UI__*` referansı).
 */

import { useEffect, useState } from "react";
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
} from "recharts";
import {
  HardDrive,
  RefreshCw,
  Trash2,
  AlertTriangle,
  CheckCircle2,
} from "lucide-react";
import { toast } from "sonner";

import {
  ApiException,
  adminDiskBreakdown,
  adminDiskCleanup,
  type DiskBreakdownResponse,
  type DiskCategory,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

// shadcn preset (radix-luma) palette uyumlu kategori renkleri (HSL).
// ui/* dokunulmuyor — color'lar burada inline (kullanım yerinde).
const CATEGORY_COLOR: Record<string, string> = {
  images: "hsl(var(--chart-1, 220 70% 50%))",
  containers: "hsl(var(--chart-2, 160 60% 45%))",
  volumes: "hsl(var(--chart-3, 30 80% 55%))",
  build_cache: "hsl(var(--chart-4, 280 65% 60%))",
  other: "hsl(var(--chart-5, 340 75% 55%))",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let v = bytes / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 ? 2 : 1)} ${units[i]}`;
}

export default function AdminDiskPage() {
  const [data, setData] = useState<DiskBreakdownResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cleanupRunning, setCleanupRunning] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const resp = await adminDiskBreakdown();
      setData(resp);
    } catch (err) {
      const e = err as ApiException;
      setError(e.message || "Disk durumu yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCleanup() {
    setCleanupRunning(true);
    setConfirmOpen(false);
    try {
      const result = await adminDiskCleanup();
      toast.success(
        `${formatBytes(result.reclaimed_bytes)} alan geri kazanıldı (${result.items_deleted} build cache item, ${result.duration_seconds}s)`,
      );
      await load();
    } catch (err) {
      const e = err as ApiException;
      toast.error(e.message || "Temizlik başarısız");
    } finally {
      setCleanupRunning(false);
    }
  }

  if (loading && !data) {
    return (
      <div className="flex items-center gap-2 p-8 text-muted-foreground">
        <RefreshCw className="h-4 w-4 animate-spin" />
        <span>Disk durumu yükleniyor…</span>
      </div>
    );
  }

  if (error && !data) {
    return (
      <Card className="border-red-200 bg-red-50 dark:bg-red-950/30">
        <CardContent className="flex items-center gap-2 py-4">
          <AlertTriangle className="h-4 w-4 text-red-600" />
          <span className="text-sm">{error}</span>
          <Button variant="outline" size="sm" onClick={load} className="ml-auto">
            Tekrar dene
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  const usedSeverity =
    data.used_percent >= 90 ? "critical" : data.used_percent >= 75 ? "warn" : "ok";
  const usedColor =
    usedSeverity === "critical"
      ? "text-red-600"
      : usedSeverity === "warn"
        ? "text-amber-600"
        : "text-emerald-600";

  // Pie chart data (sadece bytes>0 olan kategoriler)
  const chartData = data.categories
    .filter((c) => c.bytes > 0)
    .map((c) => ({
      name: c.label,
      value: c.bytes,
      key: c.key,
      reclaimable: c.reclaimable_bytes,
    }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <HardDrive className="h-6 w-6 text-accent-500" />
            VPS Disk Durumu
          </h1>
          <p className="text-sm text-muted-foreground">
            Host disk kullanımı + Docker breakdown. Build cache güvenli temizlenebilir.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw
            className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
            aria-hidden="true"
          />
          Yenile
        </Button>
      </div>

      {/* KPI cards */}
      <div className="grid gap-3 md:grid-cols-4">
        <Card>
          <CardContent className="space-y-1 py-4">
            <p className="text-xs uppercase text-muted-foreground">Toplam</p>
            <p className="text-xl font-semibold">{formatBytes(data.total_bytes)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1 py-4">
            <p className="text-xs uppercase text-muted-foreground">Kullanılan</p>
            <p className={`text-xl font-semibold ${usedColor}`}>
              {formatBytes(data.used_bytes)}{" "}
              <span className="text-sm text-muted-foreground">
                ({data.used_percent.toFixed(1)}%)
              </span>
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1 py-4">
            <p className="text-xs uppercase text-muted-foreground">Boş</p>
            <p className="text-xl font-semibold">{formatBytes(data.free_bytes)}</p>
          </CardContent>
        </Card>
        <Card
          className={data.reclaimable_bytes > 0 ? "border-amber-300 bg-amber-50/40 dark:bg-amber-950/20" : ""}
        >
          <CardContent className="space-y-1 py-4">
            <p className="text-xs uppercase text-muted-foreground">
              Geri Kazanılabilir
            </p>
            <p className="text-xl font-semibold text-amber-700 dark:text-amber-300">
              {formatBytes(data.reclaimable_bytes)}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Disk usage progress */}
      <Card>
        <CardContent className="space-y-2 py-4">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">Disk Doluluk</span>
            <span className={`font-semibold ${usedColor}`}>
              {data.used_percent.toFixed(1)}%
            </span>
          </div>
          <Progress
            value={data.used_percent}
            className={
              usedSeverity === "critical"
                ? "[&>*]:bg-red-500"
                : usedSeverity === "warn"
                  ? "[&>*]:bg-amber-500"
                  : "[&>*]:bg-emerald-500"
            }
          />
          <p className="text-xs text-muted-foreground">
            {formatBytes(data.used_bytes)} / {formatBytes(data.total_bytes)} —{" "}
            {formatBytes(data.free_bytes)} boş
          </p>
        </CardContent>
      </Card>

      {/* Pie chart + categories table */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Kullanım Dağılımı</CardTitle>
            <CardDescription>
              Docker bileşenleri + diğer (logs, system, /opt)
            </CardDescription>
          </CardHeader>
          <CardContent className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="value"
                  nameKey="name"
                  label={({ percent }) =>
                    `${((percent ?? 0) * 100).toFixed(0)}%`
                  }
                >
                  {chartData.map((entry) => (
                    <Cell
                      key={entry.key}
                      fill={CATEGORY_COLOR[entry.key] || "hsl(var(--muted))"}
                      stroke="hsl(var(--background))"
                    />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
              {chartData.map((entry) => (
                <div key={entry.key} className="flex items-center gap-2">
                  <span
                    className="h-3 w-3 flex-shrink-0 rounded-sm"
                    style={{
                      backgroundColor:
                        CATEGORY_COLOR[entry.key] || "hsl(var(--muted))",
                    }}
                    aria-hidden="true"
                  />
                  <span className="truncate">{entry.name}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Kategoriler</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Kategori</TableHead>
                  <TableHead className="text-right">Boyut</TableHead>
                  <TableHead className="text-right">Reclaimable</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.categories.map((c) => (
                  <CategoryRow key={c.key} category={c} />
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      {/* Cleanup */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Trash2 className="h-4 w-4" />
            Yer aç (build cache temizle)
          </CardTitle>
          <CardDescription>
            Sadece Docker build cache'i temizler. Image, container ve volume'lar
            ZARAR GÖRMEZ. Yaklaşık {formatBytes(
              data.categories.find((c) => c.key === "build_cache")
                ?.reclaimable_bytes ?? 0,
            )}{" "}
            geri kazanılır.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
            <DialogTrigger asChild>
              <Button
                variant="default"
                disabled={
                  cleanupRunning ||
                  (data.categories.find((c) => c.key === "build_cache")
                    ?.reclaimable_bytes ?? 0) === 0
                }
              >
                {cleanupRunning ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    Temizleniyor…
                  </>
                ) : (
                  <>
                    <Trash2 className="h-4 w-4" />
                    Yer aç
                  </>
                )}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-amber-600" />
                  Build cache temizliği
                </DialogTitle>
                <DialogDescription className="space-y-2 pt-2">
                  <span className="block">
                    `docker builder prune -af` çalıştırılacak. Bu işlem yalnızca
                    yeniden oluşturulabilir build cache layer'larını siler.
                  </span>
                  <span className="block">
                    <CheckCircle2 className="mr-1 inline h-3.5 w-3.5 text-emerald-600" />
                    Aktif container'lar zarar görmez
                  </span>
                  <span className="block">
                    <CheckCircle2 className="mr-1 inline h-3.5 w-3.5 text-emerald-600" />
                    Çalışan image'ler ve volume'lar korunur
                  </span>
                  <span className="block">
                    <CheckCircle2 className="mr-1 inline h-3.5 w-3.5 text-emerald-600" />
                    Sonraki rebuild'de cache yeniden oluşturulur (ilk build yavaş olabilir)
                  </span>
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                  Vazgeç
                </Button>
                <Button onClick={handleCleanup} disabled={cleanupRunning}>
                  Onaylıyorum, temizle
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>

      <p className="text-center text-xs text-muted-foreground">
        Son güncelleme: {new Date(data.timestamp).toLocaleString("tr-TR")}
      </p>
    </div>
  );
}

function CategoryRow({ category }: { category: DiskCategory }) {
  return (
    <TableRow>
      <TableCell>
        <div className="flex items-center gap-2">
          <span
            className="h-3 w-3 flex-shrink-0 rounded-sm"
            style={{
              backgroundColor:
                CATEGORY_COLOR[category.key] || "hsl(var(--muted))",
            }}
            aria-hidden="true"
          />
          <span className="text-sm">{category.label}</span>
        </div>
      </TableCell>
      <TableCell className="text-right font-mono text-sm">
        {formatBytes(category.bytes)}
      </TableCell>
      <TableCell className="text-right">
        {category.reclaimable_bytes > 0 ? (
          <Badge variant="outline" className="text-amber-700 dark:text-amber-300">
            {formatBytes(category.reclaimable_bytes)}
          </Badge>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </TableCell>
    </TableRow>
  );
}
