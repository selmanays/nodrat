"use client";

/**
 * /admin/plans — Plan + LS variant_id yönetimi (#77).
 *
 * LS hesap kurulduktan sonra her variant ID'sini buradan plan'a atayan admin
 * UI. Yeni variant girilmişse "Kaydet" tıklayınca PATCH; başarılıysa "available"
 * rozeti güncellenir ve `/app/billing/plans` endpoint'inde plan kullanıcıya
 * görünür hale gelir.
 *
 * Pricing/features/limits salt-okunur — bu değişimler DB migration ile yapılır
 * (audit trail).
 */

import { useEffect, useMemo, useState } from "react";
import { Check, RefreshCw, Save } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageHeader } from "@/components/blocks/page-header";
import { ApiException } from "@/lib/api";
import {
  listAdminPlans,
  updateAdminPlan,
  type AdminPlanItem,
} from "@/lib/admin-billing-api";
import { cn } from "@/lib/utils";

interface RowDraft {
  monthly: string;
  yearly: string;
  active: boolean;
  saving: boolean;
  saved: boolean;
}

function emptyDraft(plan: AdminPlanItem): RowDraft {
  return {
    monthly: plan.ls_variant_id_monthly ?? "",
    yearly: plan.ls_variant_id_yearly ?? "",
    active: plan.active,
    saving: false,
    saved: false,
  };
}

function formatUsd(value: number): string {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatTl(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return `≈${value.toLocaleString("tr-TR", { maximumFractionDigits: 0 })}₺`;
}

export default function AdminPlansPage() {
  const [plans, setPlans] = useState<AdminPlanItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [drafts, setDrafts] = useState<Record<string, RowDraft>>({});

  async function load() {
    setLoading(true);
    try {
      const resp = await listAdminPlans();
      setPlans(resp.plans);
      const next: Record<string, RowDraft> = {};
      for (const p of resp.plans) {
        next[p.code] = emptyDraft(p);
      }
      setDrafts(next);
    } catch (err) {
      toast.error((err as ApiException).message || "Plan listesi yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function dirty(plan: AdminPlanItem): boolean {
    const d = drafts[plan.code];
    if (!d) return false;
    return (
      d.monthly !== (plan.ls_variant_id_monthly ?? "") ||
      d.yearly !== (plan.ls_variant_id_yearly ?? "") ||
      d.active !== plan.active
    );
  }

  async function save(plan: AdminPlanItem) {
    const d = drafts[plan.code];
    if (!d) return;

    setDrafts((prev) => ({
      ...prev,
      [plan.code]: { ...prev[plan.code], saving: true, saved: false },
    }));

    try {
      const updated = await updateAdminPlan(plan.code, {
        ls_variant_id_monthly: d.monthly,
        ls_variant_id_yearly: d.yearly,
        active: d.active,
      });
      setPlans((prev) =>
        prev.map((p) => (p.code === updated.code ? updated : p)),
      );
      setDrafts((prev) => ({
        ...prev,
        [plan.code]: { ...emptyDraft(updated), saved: true },
      }));
      toast.success(`${updated.name} güncellendi`);
    } catch (err) {
      toast.error((err as ApiException).message || "Kaydedilemedi");
      setDrafts((prev) => ({
        ...prev,
        [plan.code]: { ...prev[plan.code], saving: false },
      }));
    }
  }

  const summary = useMemo(() => {
    const total = plans.length;
    const active = plans.filter((p) => p.active).length;
    const available = plans.filter((p) => p.available).length;
    return { total, active, available };
  }, [plans]);

  return (
    <div className="flex flex-col gap-6 p-6">
      <PageHeader
        title="Planlar"
        description={
          <>
            Lemon Squeezy variant ID atamaları + plan aktiflik durumu.
            <br />
            <span className="text-xs">
              Pricing/limits/features değişimleri DB migration ile yapılır
              (audit trail için).
            </span>
          </>
        }
        action={
          <Button
            variant="outline"
            size="sm"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw
              className={cn("mr-2 size-4", loading && "animate-spin")}
            />
            Yenile
          </Button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">Toplam plan</p>
            <p className="mt-1 text-2xl font-semibold">{summary.total}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">Aktif</p>
            <p className="mt-1 text-2xl font-semibold">{summary.active}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">
              Kullanıcıya görünen (variant atanmış)
            </p>
            <p className="mt-1 text-2xl font-semibold">{summary.available}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="space-y-2 p-6">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[140px]">Plan</TableHead>
                  <TableHead className="w-[100px]">Tier</TableHead>
                  <TableHead className="w-[140px]">Aylık fiyat</TableHead>
                  <TableHead className="w-[140px]">Yıllık fiyat</TableHead>
                  <TableHead>LS variant ID — aylık</TableHead>
                  <TableHead>LS variant ID — yıllık</TableHead>
                  <TableHead className="w-[90px]">Aktif</TableHead>
                  <TableHead className="w-[140px]">Durum</TableHead>
                  <TableHead className="w-[120px] text-right">İşlem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {plans.map((plan) => {
                  const d = drafts[plan.code] ?? emptyDraft(plan);
                  const isFree = plan.code === "free";
                  const isDirty = dirty(plan);
                  return (
                    <TableRow key={plan.code}>
                      <TableCell>
                        <div className="font-medium">{plan.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {plan.code}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{plan.tier}</Badge>
                      </TableCell>
                      <TableCell>
                        <div>{formatUsd(plan.price_usd_monthly)}</div>
                        <div className="text-xs text-muted-foreground">
                          {formatTl(plan.price_tl_display_monthly)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div>{formatUsd(plan.price_usd_yearly)}</div>
                        <div className="text-xs text-muted-foreground">
                          {formatTl(plan.price_tl_display_yearly)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Input
                          value={d.monthly}
                          disabled={isFree || d.saving}
                          placeholder={isFree ? "—" : "örn. 123456"}
                          onChange={(e) =>
                            setDrafts((prev) => ({
                              ...prev,
                              [plan.code]: {
                                ...prev[plan.code],
                                monthly: e.target.value,
                                saved: false,
                              },
                            }))
                          }
                          className="h-8 font-mono text-xs"
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          value={d.yearly}
                          disabled={isFree || d.saving}
                          placeholder={isFree ? "—" : "örn. 123457"}
                          onChange={(e) =>
                            setDrafts((prev) => ({
                              ...prev,
                              [plan.code]: {
                                ...prev[plan.code],
                                yearly: e.target.value,
                                saved: false,
                              },
                            }))
                          }
                          className="h-8 font-mono text-xs"
                        />
                      </TableCell>
                      <TableCell>
                        <Switch
                          checked={d.active}
                          disabled={d.saving}
                          onCheckedChange={(checked) =>
                            setDrafts((prev) => ({
                              ...prev,
                              [plan.code]: {
                                ...prev[plan.code],
                                active: checked,
                                saved: false,
                              },
                            }))
                          }
                        />
                      </TableCell>
                      <TableCell>
                        {plan.available ? (
                          <Badge className="bg-emerald-600 hover:bg-emerald-600">
                            Görünür
                          </Badge>
                        ) : isFree ? (
                          <Badge variant="secondary">Ücretsiz</Badge>
                        ) : (
                          <Badge variant="outline">Yakında</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant={isDirty ? "default" : "outline"}
                          disabled={!isDirty || d.saving}
                          onClick={() => void save(plan)}
                        >
                          {d.saving ? (
                            <RefreshCw className="mr-1 size-3 animate-spin" />
                          ) : d.saved && !isDirty ? (
                            <Check className="mr-1 size-3" />
                          ) : (
                            <Save className="mr-1 size-3" />
                          )}
                          Kaydet
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card className="border-dashed">
        <CardContent className="p-4 text-xs text-muted-foreground">
          <strong className="text-foreground">Variant ID nereden alınır?</strong>{" "}
          Lemon Squeezy dashboard → Products → Variant satırı → URL'deki sayısal
          ID. Aylık ve yıllık variant'lar ayrı ayrı atanmalı. Variant
          atanmadan plan kullanıcıya görünmez (`/app/billing/plans` endpoint'i
          `available: false` döner).
        </CardContent>
      </Card>
    </div>
  );
}
