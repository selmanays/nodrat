"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, History, RotateCcw } from "lucide-react";
import { toast } from "sonner";

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
  ApiException,
  getSource,
  listConfigs,
  rollbackConfig,
  type ConfigListResponse,
  type SourceConfigPublic,
  type SourcePublic,
} from "@/lib/api";

export default function SourceConfigVersionsPage() {
  const params = useParams<{ id: string }>();
  const sourceId = params?.id ?? "";

  const [source, setSource] = useState<SourcePublic | null>(null);
  const [data, setData] = useState<ConfigListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [compareWith, setCompareWith] = useState<number | null>(null);

  async function load() {
    if (!sourceId) return;
    setLoading(true);
    try {
      const [src, configs] = await Promise.all([
        getSource(sourceId),
        listConfigs(sourceId),
      ]);
      setSource(src);
      setData(configs);
      // Default selection: aktif version
      if (configs.active_version != null) {
        setSelected(configs.active_version);
      } else if (configs.items.length > 0) {
        setSelected(configs.items[0].version);
      }
    } catch (e) {
      toast.error(e instanceof ApiException ? e.message : "Yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceId]);

  const selectedCfg = useMemo(
    () => data?.items.find((c) => c.version === selected) ?? null,
    [data, selected],
  );
  const compareCfg = useMemo(
    () => data?.items.find((c) => c.version === compareWith) ?? null,
    [data, compareWith],
  );

  async function handleRollback(version: number) {
    if (!confirm(`v${version} aktif edilsin mi? (rollback)`)) return;
    setBusy(true);
    try {
      await rollbackConfig(sourceId, version);
      toast.success(`v${version} aktif edildi`);
      await load();
    } catch (e) {
      toast.error(e instanceof ApiException ? e.message : "Rollback başarısız");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="container max-w-6xl py-10">
        <p className="text-muted-foreground">Yükleniyor…</p>
      </div>
    );
  }

  if (!source || !data) {
    return (
      <div className="container max-w-6xl py-10">
        <p className="text-destructive">Veri yüklenemedi.</p>
      </div>
    );
  }

  return (
    <div className="container max-w-6xl py-8 space-y-6">
      <div className="flex items-center gap-3">
        <Button asChild variant="ghost" size="sm">
          <Link href={`/admin/sources/${sourceId}`}>
            <ArrowLeft className="mr-1 h-4 w-4" /> Kaynak detayı
          </Link>
        </Button>
        <h1 className="text-xl font-semibold">
          Config versiyonları — {source.name}
        </h1>
        <History className="h-4 w-4 text-muted-foreground" />
      </div>

      <p className="text-sm text-muted-foreground">
        SourceConfig version geçmişi. Aktif version crawl'da kullanılır. Diff
        viewer eski version'larla karşılaştırma için. Rollback eski version'i
        tek tıkla aktif eder (audit log'a kaydedilir).
      </p>

      <div className="grid gap-6 md:grid-cols-[260px_1fr]">
        {/* Version list */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">
              {data.total} version
            </CardTitle>
            <CardDescription>
              Aktif: v{data.active_version ?? "—"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-1">
            {data.items.length === 0 && (
              <p className="text-xs text-muted-foreground">Hiç config yok.</p>
            )}
            {data.items.map((cfg) => (
              <button
                key={cfg.id}
                onClick={() => setSelected(cfg.version)}
                className={`w-full text-left px-2 py-1.5 rounded border text-sm hover:bg-muted ${
                  selected === cfg.version ? "border-primary bg-muted" : ""
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono">v{cfg.version}</span>
                  {cfg.is_active && (
                    <Badge variant="default" className="text-[10px]">
                      aktif
                    </Badge>
                  )}
                </div>
                <div className="text-xs text-muted-foreground">
                  {new Date(cfg.created_at).toLocaleString("tr-TR")}
                </div>
              </button>
            ))}
          </CardContent>
        </Card>

        {/* Detail / diff */}
        <div className="space-y-4">
          {selectedCfg ? (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <CardTitle className="text-base">
                      Version {selectedCfg.version}{" "}
                      {selectedCfg.is_active && (
                        <Badge variant="default" className="ml-2">
                          aktif
                        </Badge>
                      )}
                    </CardTitle>
                    <CardDescription>
                      {new Date(selectedCfg.created_at).toLocaleString("tr-TR")}
                    </CardDescription>
                  </div>
                  {!selectedCfg.is_active && (
                    <Button
                      size="sm"
                      onClick={() => handleRollback(selectedCfg.version)}
                      disabled={busy}
                    >
                      <RotateCcw className="mr-1 h-3 w-3" />
                      Bu version'a dön
                    </Button>
                  )}
                </div>
                <div className="flex items-center gap-2 pt-2">
                  <span className="text-xs text-muted-foreground">
                    Karşılaştır:
                  </span>
                  <select
                    value={compareWith ?? ""}
                    onChange={(e) =>
                      setCompareWith(
                        e.target.value === "" ? null : Number(e.target.value),
                      )
                    }
                    className="text-xs h-7 rounded border bg-background px-2"
                  >
                    <option value="">— yok —</option>
                    {data.items
                      .filter((c) => c.version !== selectedCfg.version)
                      .map((c) => (
                        <option key={c.id} value={c.version}>
                          v{c.version}
                          {c.is_active ? " (aktif)" : ""}
                        </option>
                      ))}
                  </select>
                </div>
              </CardHeader>
              <CardContent>
                {compareCfg ? (
                  <DiffView left={compareCfg} right={selectedCfg} />
                ) : (
                  <pre className="text-xs bg-muted p-3 rounded max-h-[500px] overflow-auto">
                    {JSON.stringify(selectedCfg.config_json, null, 2)}
                  </pre>
                )}
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground text-sm">
                Soldan bir version seç.
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Diff viewer — basit JSON karşılaştırması (key-by-key)
// =============================================================================

function DiffView({
  left,
  right,
}: {
  left: SourceConfigPublic;
  right: SourceConfigPublic;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 text-xs">
      <DiffSide
        title={`v${left.version}${left.is_active ? " (aktif)" : ""}`}
        json={left.config_json}
        otherJson={right.config_json}
      />
      <DiffSide
        title={`v${right.version}${right.is_active ? " (aktif)" : ""}`}
        json={right.config_json}
        otherJson={left.config_json}
        isRight
      />
    </div>
  );
}

function DiffSide({
  title,
  json,
  otherJson,
  isRight = false,
}: {
  title: string;
  json: Record<string, unknown>;
  otherJson: Record<string, unknown>;
  isRight?: boolean;
}) {
  const lines = JSON.stringify(json, null, 2).split("\n");
  const otherLines = JSON.stringify(otherJson, null, 2).split("\n");
  return (
    <div>
      <div className="text-[11px] font-mono mb-1 text-muted-foreground">
        {title}
      </div>
      <pre className="bg-muted p-3 rounded max-h-[500px] overflow-auto leading-5">
        {lines.map((line, i) => {
          const inOther = otherLines.includes(line);
          const cls = !inOther
            ? isRight
              ? "bg-green-500/15"
              : "bg-red-500/15"
            : "";
          return (
            <div key={i} className={`${cls} px-1 -mx-1`}>
              {line || " "}
            </div>
          );
        })}
      </pre>
    </div>
  );
}
