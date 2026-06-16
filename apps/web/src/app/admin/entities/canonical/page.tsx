"use client";

/**
 * Admin Canonical Entities — merge/split/manuel alias yönetimi (#1554).
 *
 * Deterministik builder'ın çözemediği belirsiz vakaları (örn. "2026 Dünya
 * Kupası" → FIFA; okçuluk yüzünden otomatik birleşmez) admin elle çözer:
 *  - Birleştir (merge): bir grubu başka gruba kat (kaynak silinir, alias'lar taşınır).
 *  - Ayır (split): bir varyantı gruptan çıkar.
 *  - Manuel alias ekle / yeni canonical oluştur.
 * Mutation → backend audit + alias source='admin' → builder bunları EZMEZ.
 */

import { useCallback, useEffect, useState } from "react";
import { Combine, Plus, RefreshCw, Search, X } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/blocks/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  type CanonicalDetailResponse,
  type CanonicalEntityType,
  type CanonicalRow,
  addAliases,
  createCanonical,
  getCanonical,
  listCanonical,
  mergeCanonical,
  removeAlias,
} from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  person: "Kişi",
  org: "Kurum",
  place: "Yer",
  event: "Olay",
};
const TYPES: CanonicalEntityType[] = ["person", "org", "place", "event"];
const SOURCE_LABEL: Record<string, string> = {
  admin: "manuel",
  seed: "seed",
  token_subset: "token-altküme",
};

function fmt(n: number): string {
  return n.toLocaleString("tr-TR");
}

function errMsg(e: unknown): string {
  const ex = e as { title?: string; detail?: string };
  return ex?.detail || ex?.title || "İşlem başarısız";
}

export default function AdminCanonicalEntitiesPage() {
  const [rows, setRows] = useState<CanonicalRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");

  const [detail, setDetail] = useState<CanonicalDetailResponse | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listCanonical({
        search: search.trim() || undefined,
        entity_type: typeFilter === "all" ? undefined : (typeFilter as CanonicalEntityType),
        limit: 100,
      });
      setRows(res.data);
      setTotal(res.total);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, [search, typeFilter]);

  // debounce: search/filter değişince 350ms sonra yükle
  useEffect(() => {
    const t = setTimeout(() => void load(), 350);
    return () => clearTimeout(t);
  }, [load]);

  const openDetail = useCallback(async (id: string) => {
    setDetailOpen(true);
    setDetail(null);
    try {
      setDetail(await getCanonical(id));
    } catch (e) {
      toast.error(errMsg(e));
      setDetailOpen(false);
    }
  }, []);

  const refreshDetail = useCallback(async (id: string) => {
    try {
      setDetail(await getCanonical(id));
    } catch (e) {
      toast.error(errMsg(e));
    }
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Varlık Birleştirme"
        description="Aynı şeyi işaret eden varlık varyantlarını grupla — birleştir, ayır, manuel alias ekle. Değişiklikler denetim kaydına geçer ve otomatik builder tarafından ezilmez."
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Canonical ara…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-[140px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tüm tipler</SelectItem>
            {TYPES.map((t) => (
              <SelectItem key={t} value={t}>
                {TYPE_LABEL[t]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" size="icon" onClick={() => void load()} title="Yenile">
          <RefreshCw className="h-4 w-4" />
        </Button>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> Yeni canonical
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Canonical ad</TableHead>
                <TableHead className="w-[90px]">Tip</TableHead>
                <TableHead className="w-[110px] text-right">Varyant</TableHead>
                <TableHead className="w-[120px]">Kaynak</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={4}>
                      <Skeleton className="h-5 w-full" />
                    </TableCell>
                  </TableRow>
                ))
              ) : rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="py-10 text-center text-muted-foreground">
                    Canonical grup yok. Builder henüz çalışmamış olabilir veya filtre eşleşmedi.
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((r) => (
                  <TableRow
                    key={r.id}
                    className="cursor-pointer"
                    onClick={() => void openDetail(r.id)}
                  >
                    <TableCell className="font-medium">{r.canonical_name}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{TYPE_LABEL[r.entity_type] ?? r.entity_type}</Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{fmt(r.alias_count)}</TableCell>
                    <TableCell>
                      <Badge variant={r.source === "admin" ? "default" : "outline"}>
                        {SOURCE_LABEL[r.source] ?? r.source}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      {!loading && rows.length > 0 ? (
        <p className="text-xs text-muted-foreground">
          {fmt(rows.length)} / {fmt(total)} grup gösteriliyor
        </p>
      ) : null}

      <DetailDialog
        open={detailOpen}
        onOpenChange={setDetailOpen}
        detail={detail}
        onChanged={async (id) => {
          await refreshDetail(id);
          await load();
        }}
        onMerged={async () => {
          setDetailOpen(false);
          await load();
        }}
      />

      <CreateDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={async () => {
          setCreateOpen(false);
          await load();
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detay diyalog: alias listesi + ayır + manuel ekle + birleştir
// ---------------------------------------------------------------------------

function DetailDialog({
  open,
  onOpenChange,
  detail,
  onChanged,
  onMerged,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  detail: CanonicalDetailResponse | null;
  onChanged: (id: string) => Promise<void>;
  onMerged: () => Promise<void>;
}) {
  const [newAlias, setNewAlias] = useState("");
  const [mergeSearch, setMergeSearch] = useState("");
  const [mergeCandidates, setMergeCandidates] = useState<CanonicalRow[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setNewAlias("");
      setMergeSearch("");
    }
  }, [open, detail?.canonical.id]);

  const canon = detail?.canonical;
  const canonId = canon?.id;
  const canonType = canon?.entity_type;

  // birleştirme adayları: sunucu-taraflı arama (listCanonical, #1558 alias-aware) —
  // aynı tip + kendini ele. allRows yerine: alias'ları da kapsar + tüm veriyi tarar
  // (yüklü ≤100 satırla sınırlı değil). debounce 300ms.
  useEffect(() => {
    if (!open || !canonId || !canonType) {
      setMergeCandidates([]);
      return;
    }
    const t = setTimeout(() => {
      void (async () => {
        try {
          const res = await listCanonical({
            search: mergeSearch.trim() || undefined,
            entity_type: canonType as CanonicalEntityType,
            limit: 10,
          });
          setMergeCandidates(res.data.filter((r) => r.id !== canonId).slice(0, 8));
        } catch {
          setMergeCandidates([]);
        }
      })();
    }, 300);
    return () => clearTimeout(t);
  }, [open, canonId, canonType, mergeSearch]);

  async function handleAddAlias() {
    if (!canon || !newAlias.trim()) return;
    setBusy(true);
    try {
      await addAliases(
        canon.id,
        newAlias.split(",").map((s) => s.trim()).filter(Boolean),
      );
      setNewAlias("");
      toast.success("Varyant eklendi");
      await onChanged(canon.id);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(alias: string) {
    if (!canon) return;
    setBusy(true);
    try {
      await removeAlias(canon.id, alias);
      toast.success("Varyant ayrıldı");
      await onChanged(canon.id);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleMerge(sourceId: string, sourceName: string) {
    if (!canon) return;
    setBusy(true);
    try {
      await mergeCanonical(canon.id, sourceId);
      toast.success(`"${sourceName}" bu gruba katıldı`);
      await onMerged();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        {!detail || !canon ? (
          <div className="space-y-3 py-4">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {canon.canonical_name}
                <Badge variant="secondary">
                  {TYPE_LABEL[canon.entity_type] ?? canon.entity_type}
                </Badge>
              </DialogTitle>
              <DialogDescription>
                {fmt(detail.aliases.length)} varyant bu gruba bağlı. Bir varyantı
                ayırmak için ×'e bas; başka bir grubu bu gruba katmak için aşağıdan seç.
              </DialogDescription>
            </DialogHeader>

            {/* Alias listesi */}
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">Varyantlar</Label>
              <div className="flex flex-wrap gap-1.5">
                {detail.aliases.length === 0 ? (
                  <span className="text-sm text-muted-foreground">Henüz varyant yok.</span>
                ) : (
                  detail.aliases.map((a) => (
                    <Badge
                      key={a.alias_normalized}
                      variant="outline"
                      className="gap-1 pr-1 font-normal"
                      title={`kaynak: ${SOURCE_LABEL[a.source] ?? a.source}`}
                    >
                      {a.alias_normalized}
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void handleRemove(a.alias_normalized)}
                        className="rounded-sm hover:bg-destructive/20 disabled:opacity-50"
                        title="Bu varyantı ayır"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))
                )}
              </div>
            </div>

            {/* Manuel alias ekle */}
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">
                Varyant ekle (virgülle çoklu)
              </Label>
              <div className="flex gap-2">
                <Input
                  value={newAlias}
                  onChange={(e) => setNewAlias(e.target.value)}
                  placeholder="örn. cumhurbaşkanı erdoğan"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void handleAddAlias();
                    }
                  }}
                />
                <Button onClick={() => void handleAddAlias()} disabled={busy || !newAlias.trim()}>
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Birleştir */}
            <div className="space-y-2 border-t pt-3">
              <Label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Combine className="h-3.5 w-3.5" /> Başka grubu bu gruba kat
              </Label>
              <Input
                value={mergeSearch}
                onChange={(e) => setMergeSearch(e.target.value)}
                placeholder="Birleştirilecek grubu ara…"
              />
              <div className="max-h-40 space-y-1 overflow-y-auto">
                {mergeCandidates.length === 0 ? (
                  <p className="px-1 py-2 text-xs text-muted-foreground">
                    Aynı tipte ({TYPE_LABEL[canon.entity_type]}) eşleşen başka grup yok.
                  </p>
                ) : (
                  mergeCandidates.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      disabled={busy}
                      onClick={() => void handleMerge(c.id, c.canonical_name)}
                      className="flex w-full items-center justify-between rounded-md border px-2.5 py-1.5 text-left text-sm hover:bg-accent disabled:opacity-50"
                    >
                      <span>
                        {c.canonical_name}
                        <span className="ml-1.5 text-xs text-muted-foreground">
                          ({fmt(c.alias_count)} varyant)
                        </span>
                      </span>
                      <Combine className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Yeni canonical diyalog
// ---------------------------------------------------------------------------

function CreateDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated: () => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState<CanonicalEntityType>("person");
  const [aliases, setAliases] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setName("");
      setType("person");
      setAliases("");
    }
  }, [open]);

  async function handleCreate() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await createCanonical({
        canonical_name: name.trim(),
        entity_type: type,
        aliases: aliases
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      toast.success("Canonical oluşturuldu");
      await onCreated();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Yeni canonical grup</DialogTitle>
          <DialogDescription>
            Kanonik adı + tip belirle. İstersen varyantları virgülle ekle.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="cc-name">Kanonik ad</Label>
            <Input
              id="cc-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="örn. Recep Tayyip Erdoğan"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Tip</Label>
            <Select value={type} onValueChange={(v) => setType(v as CanonicalEntityType)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {TYPE_LABEL[t]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cc-aliases">Varyantlar (virgülle, opsiyonel)</Label>
            <Input
              id="cc-aliases"
              value={aliases}
              onChange={(e) => setAliases(e.target.value)}
              placeholder="cumhurbaşkanı erdoğan, tayyip erdoğan"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Vazgeç
          </Button>
          <Button onClick={() => void handleCreate()} disabled={busy || !name.trim()}>
            Oluştur
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
