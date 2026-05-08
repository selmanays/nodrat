"use client";

/**
 * /app/billing/invoices — LS invoice referans listesi (#76).
 *
 * Backend GET /app/billing/invoices → LS invoice cache.
 * Gerçek PDF Lemon Squeezy'de hosted; ls_invoice_url signed link (TTL'li).
 * Nodrat fatura kesmez (LS MoR keser, KDV global handling).
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Download,
  ExternalLink,
  FileText,
  Loader2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiException } from "@/lib/api";
import {
  listInvoices,
  type InvoiceItem,
} from "@/lib/billing-api";
import { formatTrDate } from "@/lib/format";


export default function BillingInvoicesPage() {
  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await listInvoices();
        setInvoices(res.data);
      } catch (err) {
        const msg =
          err instanceof ApiException
            ? err.message
            : "Faturalar yüklenemedi.";
        setError(msg);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <Button variant="ghost" size="sm" asChild className="mb-2">
          <Link href="/app/billing">
            <ArrowLeft className="size-4" />
            Plan ve Faturalama
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold tracking-tight">Faturalarım</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Faturalar Lemon Squeezy (Merchant of Record) tarafından kesilir.
          KDV/VAT/sales tax fiyata dahildir. Tüm tutarlar USD primary; PDF'ler
          Lemon Squeezy hosted (kısa süreli signed link).
        </p>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Faturalar yükleniyor…
        </div>
      )}

      {error && (
        <Card>
          <CardHeader>
            <CardTitle>Hata</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
        </Card>
      )}

      {!loading && !error && invoices.length === 0 && (
        <Card className="border-dashed">
          <CardHeader className="text-center">
            <div className="mx-auto mb-2 flex size-10 items-center justify-center rounded-full bg-muted">
              <FileText className="size-5 text-muted-foreground" />
            </div>
            <CardTitle>Henüz fatura yok</CardTitle>
            <CardDescription>
              İlk fatura, ilk ödemen başarıyla işlendiğinde burada görünecek.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <Button asChild variant="outline">
              <Link href="/app/billing">Plan seç</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {!loading && !error && invoices.length > 0 && (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tarih</TableHead>
                <TableHead>LS Invoice ID</TableHead>
                <TableHead className="text-right">Tutar</TableHead>
                <TableHead className="text-right">KDV/VAT</TableHead>
                <TableHead className="text-right">Toplam</TableHead>
                <TableHead className="w-[80px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invoices.map((inv) => (
                <TableRow key={inv.id}>
                  <TableCell className="font-mono text-xs">
                    {formatTrDate(inv.issued_at)}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {inv.ls_invoice_id.slice(0, 12)}…
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    ${inv.amount_usd.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {inv.tax_amount_usd != null
                      ? `$${inv.tax_amount_usd.toFixed(2)}`
                      : "—"}
                  </TableCell>
                  <TableCell className="text-right font-medium tabular-nums">
                    ${inv.total_usd.toFixed(2)} {inv.currency}
                  </TableCell>
                  <TableCell>
                    {inv.ls_invoice_url ? (
                      <Button asChild variant="ghost" size="icon-sm">
                        <a
                          href={inv.ls_invoice_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label="LS hosted PDF'i indir"
                        >
                          <Download className="size-4" />
                        </a>
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <CardContent className="border-t pt-3 text-xs text-muted-foreground">
            <p>
              <strong>Bilgi:</strong> Lemon Squeezy hosted PDF link'leri kısa
              süreli geçerli (signed URL TTL). İstediğin zaman bu sayfadan tekrar
              indirebilirsin.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
        <Link href="/legal/refund-policy" className="underline hover:text-foreground" target="_blank">
          İade Politikası
        </Link>
        <span>·</span>
        <Link href="/legal/mesafeli-satis-sozlesmesi" className="underline hover:text-foreground" target="_blank">
          Mesafeli Satış Sözleşmesi
        </Link>
        <span>·</span>
        <Link href="/app/billing/manage" className="underline hover:text-foreground inline-flex items-center gap-1">
          <ExternalLink className="size-3" />
          LS Customer Portal
        </Link>
      </div>
    </div>
  );
}
