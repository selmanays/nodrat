"use client";

import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Cpu,
  Database,
  HardDrive,
  HeartPulse,
  RefreshCw,
  Server,
} from "lucide-react";

import {
  adminSystemHealth,
  type SystemHealthResponse,
} from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";


function formatBytes(gb: number): string {
  if (gb >= 1) return `${gb.toFixed(2)} GB`;
  return `${(gb * 1024).toFixed(1)} MB`;
}

function statusBadge(usedPct: number, criticalThreshold = 85): "default" | "secondary" | "destructive" {
  if (usedPct >= criticalThreshold) return "destructive";
  if (usedPct >= 70) return "secondary";
  return "default";
}

const REFRESH_INTERVAL_MS = 30_000;


export default function ObservabilityPage() {
  const [data, setData] = useState<SystemHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);
    adminSystemHealth()
      .then((r) => {
        if (mounted) {
          setData(r);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (mounted) {
          setError(e?.message || "fetch failed");
          setLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, [refreshTrigger]);

  // Auto-refresh
  useEffect(() => {
    const interval = setInterval(() => {
      setRefreshTrigger((t) => t + 1);
    }, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <HeartPulse className="h-7 w-7" /> Sistem Durumu
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            VPS, PostgreSQL, MinIO, Contabo Object Storage, backup durumu — auto-refresh 30s
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setRefreshTrigger((t) => t + 1)}
          disabled={loading}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Yenile
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Hata</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {data && data.vps.disk.used_pct >= 85 && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>VPS disk kritik</AlertTitle>
          <AlertDescription>
            Disk kullanımı {data.vps.disk.used_pct}% — cold tier flush + cleanup gerekebilir
          </AlertDescription>
        </Alert>
      )}

      {data && data.vps.ram.used_pct >= 90 && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>VPS RAM kritik</AlertTitle>
          <AlertDescription>
            RAM kullanımı {data.vps.ram.used_pct}% — worker concurrency'i azalt veya VPS upgrade
          </AlertDescription>
        </Alert>
      )}

      {data && data.backups.last_snapshot_age_h !== null && data.backups.last_snapshot_age_h > 36 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Backup geç</AlertTitle>
          <AlertDescription>
            Son snapshot {data.backups.last_snapshot_age_h.toFixed(1)} saat önce — restic cron'unu kontrol et
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* VPS Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Server className="h-5 w-5" /> VPS
            </CardTitle>
            <CardDescription>
              {loading ? <Skeleton className="h-4 w-32" /> : data?.vps.hostname}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {loading ? (
              <Skeleton className="h-32 w-full" />
            ) : data ? (
              <>
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="flex items-center gap-2">
                      <Cpu className="h-4 w-4" /> CPU ({data.vps.cpu.cores} cores)
                    </span>
                    <Badge variant={statusBadge(data.vps.cpu.usage_pct)}>
                      load {data.vps.cpu.load_1m} | {data.vps.cpu.usage_pct}%
                    </Badge>
                  </div>
                  <Progress value={data.vps.cpu.usage_pct} />
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="flex items-center gap-2">
                      <Activity className="h-4 w-4" /> RAM
                    </span>
                    <Badge variant={statusBadge(data.vps.ram.used_pct, 90)}>
                      {data.vps.ram.used_mb}/{data.vps.ram.total_mb} MB ({data.vps.ram.used_pct}%)
                    </Badge>
                  </div>
                  <Progress value={data.vps.ram.used_pct} />
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="flex items-center gap-2">
                      <HardDrive className="h-4 w-4" /> Disk
                    </span>
                    <Badge variant={statusBadge(data.vps.disk.used_pct, 85)}>
                      {data.vps.disk.used_gb}/{data.vps.disk.total_gb} GB ({data.vps.disk.used_pct}%)
                    </Badge>
                  </div>
                  <Progress value={data.vps.disk.used_pct} />
                </div>
              </>
            ) : null}
          </CardContent>
        </Card>

        {/* Postgres Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="h-5 w-5" /> PostgreSQL
            </CardTitle>
            <CardDescription>
              Toplam: {loading ? <Skeleton className="h-4 w-16 inline-block" /> : `${data?.postgres.db_size_gb} GB`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-48 w-full" />
            ) : data ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tablo</TableHead>
                    <TableHead className="text-right">Boyut</TableHead>
                    <TableHead className="text-right">Satır</TableHead>
                    <TableHead className="text-right">Index</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.postgres.tables.slice(0, 10).map((t) => (
                    <TableRow key={t.name}>
                      <TableCell className="font-mono text-xs">{t.name}</TableCell>
                      <TableCell className="text-right">{t.size_mb} MB</TableCell>
                      <TableCell className="text-right text-muted-foreground">{t.row_count.toLocaleString("tr-TR")}</TableCell>
                      <TableCell className="text-right text-muted-foreground">{t.index_size_mb} MB</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : null}
          </CardContent>
        </Card>

        {/* MinIO Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HardDrive className="h-5 w-5" /> MinIO (Hot Storage)
            </CardTitle>
            <CardDescription className="font-mono text-xs">
              {loading ? <Skeleton className="h-4 w-48" /> : data?.minio.endpoint}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-32 w-full" />
            ) : data && data.minio.buckets.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Bucket</TableHead>
                    <TableHead className="text-right">Boyut</TableHead>
                    <TableHead className="text-right">Object</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.minio.buckets.map((b) => (
                    <TableRow key={b.name}>
                      <TableCell className="font-mono text-xs">{b.name}</TableCell>
                      <TableCell className="text-right">{formatBytes(b.size_gb)}</TableCell>
                      <TableCell className="text-right text-muted-foreground">{b.object_count.toLocaleString("tr-TR")}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="text-sm text-muted-foreground">Bucket yok</p>
            )}
          </CardContent>
        </Card>

        {/* Contabo Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HardDrive className="h-5 w-5" /> Contabo Object Storage (Cold/Backup)
            </CardTitle>
            <CardDescription className="font-mono text-xs">
              {loading ? <Skeleton className="h-4 w-48" /> : `${data?.contabo_os.bucket} @ ${data?.contabo_os.endpoint}`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-32 w-full" />
            ) : data ? (
              <div className="space-y-3">
                <div className="flex justify-between items-baseline">
                  <span className="text-sm">Toplam:</span>
                  <Badge variant="default">
                    {formatBytes(data.contabo_os.size_gb)} / {data.contabo_os.object_count.toLocaleString("tr-TR")} object
                  </Badge>
                </div>
                {Object.keys(data.contabo_os.by_prefix).length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Prefix</TableHead>
                        <TableHead className="text-right">Boyut</TableHead>
                        <TableHead className="text-right">Object</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {Object.entries(data.contabo_os.by_prefix).map(([prefix, info]) => (
                        <TableRow key={prefix}>
                          <TableCell className="font-mono text-xs">{prefix}</TableCell>
                          <TableCell className="text-right">{formatBytes(info.size_gb)}</TableCell>
                          <TableCell className="text-right text-muted-foreground">{info.object_count.toLocaleString("tr-TR")}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="text-sm text-muted-foreground">Henüz object yok</p>
                )}
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* Backup Card */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" /> Backup (Restic)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-16 w-full" />
            ) : data ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Durum</p>
                  <Badge
                    variant={data.backups.last_check_status === "ok" ? "default" : "secondary"}
                  >
                    {data.backups.last_check_status}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Snapshot sayısı</p>
                  <p className="text-2xl font-bold">{data.backups.snapshot_count}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Son snapshot</p>
                  <p className="text-2xl font-bold">
                    {data.backups.last_snapshot_age_h !== null
                      ? `${data.backups.last_snapshot_age_h.toFixed(1)} saat önce`
                      : "—"}
                  </p>
                </div>
              </div>
            ) : null}
            {data?.backups.last_check_status === "restic_not_installed" && (
              <p className="text-sm text-muted-foreground mt-3">
                ℹ️ Restic API container'ında yüklü değil. Backup metrikleri için cron job sonuçları DB'ye kaydedilmeli (gelecek geliştirme).
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {data && (
        <p className="text-xs text-muted-foreground text-center">
          Son güncelleme: {new Date(data.timestamp).toLocaleString("tr-TR")} | cache yaşı: {data.cache_age_seconds}s
        </p>
      )}
    </div>
  );
}
