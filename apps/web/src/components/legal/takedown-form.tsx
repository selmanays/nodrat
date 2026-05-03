"use client";

import { FormEvent, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiException, apiFetch } from "@/lib/api";

interface Props {
  endpoint: "abuse" | "takedown" | "copyright" | "privacy-request";
  title: string;
  description: string;
  authorityHint: string;
  /** Sayfa kapsamında zorunlu field'lar — 'subject_url' yasal taleplerde zorunlu */
  requireSubjectUrl?: boolean;
}

interface SubmissionResponse {
  ticket_id: string;
  request_type: string;
  status: string;
  sla_due_at: string;
  message: string;
}

export function TakedownForm({
  endpoint,
  title,
  description,
  authorityHint,
  requireSubjectUrl = false,
}: Props) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [organization, setOrganization] = useState("");
  const [authority, setAuthority] = useState("");
  const [subjectUrl, setSubjectUrl] = useState("");
  const [message, setMessage] = useState("");
  const [evidenceUrls, setEvidenceUrls] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState<SubmissionResponse | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (message.trim().length < 20) {
      toast.error("Açıklama en az 20 karakter olmalı");
      return;
    }
    if (requireSubjectUrl && !subjectUrl.trim()) {
      toast.error("Şikayete konu URL zorunlu");
      return;
    }

    setSubmitting(true);
    try {
      const evidence_urls = evidenceUrls
        .split(/[\n,]/)
        .map((u) => u.trim())
        .filter((u) => u.startsWith("http"));

      const response = await apiFetch<SubmissionResponse>(`/legal/${endpoint}`, {
        method: "POST",
        skipAuth: true,
        body: {
          requester_email: email,
          requester_name: name || null,
          requester_phone: phone || null,
          requester_organization: organization || null,
          authority_claim: authority || null,
          subject_url: subjectUrl || null,
          description: message,
          evidence_urls,
        },
      });
      setSubmitted(response);
      toast.success(`Talebiniz alındı: ${response.ticket_id}`);
    } catch (error) {
      const apiError = error as ApiException;
      toast.error(apiError.message || "Talep iletilemedi");
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <Card className="not-prose border-emerald-200 bg-emerald-50 dark:bg-emerald-950/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-emerald-900 dark:text-emerald-100">
            <CheckCircle2 className="h-5 w-5" />
            Talebiniz alındı
          </CardTitle>
          <CardDescription className="text-emerald-800 dark:text-emerald-200">
            {submitted.message}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p>
            <span className="font-medium">Talep numarası:</span>{" "}
            <span className="font-mono text-base">{submitted.ticket_id}</span>
          </p>
          <p>
            <span className="font-medium">Triaj SLA:</span>{" "}
            {new Date(submitted.sla_due_at).toLocaleString("tr-TR")}
          </p>
          <p className="text-xs text-muted-foreground">
            Bu numarayı kaydedin. Sürecin durumunu sorgulamak için bizimle{" "}
            <a
              href={`mailto:legal@nodrat.com?subject=${submitted.ticket_id}`}
              className="text-brand-700 hover:underline"
            >
              legal@nodrat.com
            </a>{" "}
            üzerinden iletişime geçebilirsiniz.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="not-prose">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="name">Ad Soyad</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={180}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="email">E-posta *</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="phone">Telefon (opsiyonel)</Label>
              <Input
                id="phone"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                maxLength={40}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="org">Kurum / Şirket (opsiyonel)</Label>
              <Input
                id="org"
                value={organization}
                onChange={(e) => setOrganization(e.target.value)}
                maxLength={180}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="authority">Hangi sıfatla başvuruyorsunuz?</Label>
            <Input
              id="authority"
              placeholder={authorityHint}
              value={authority}
              onChange={(e) => setAuthority(e.target.value)}
              maxLength={500}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="subject_url">
              Şikayete konu URL{" "}
              {requireSubjectUrl && <span className="text-error">*</span>}
            </Label>
            <Input
              id="subject_url"
              type="url"
              placeholder="https://nodrat.com/... veya kaynak haber URL'si"
              required={requireSubjectUrl}
              value={subjectUrl}
              onChange={(e) => setSubjectUrl(e.target.value)}
              maxLength={2000}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="description">
              Açıklama * (en az 20 karakter)
            </Label>
            <Textarea
              id="description"
              required
              minLength={20}
              maxLength={5000}
              rows={6}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              {message.length}/5000
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="evidence">Kanıt URL'leri (opsiyonel)</Label>
            <Textarea
              id="evidence"
              rows={3}
              placeholder="Her satıra bir URL"
              value={evidenceUrls}
              onChange={(e) => setEvidenceUrls(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Her satıra bir URL — http:// veya https:// ile başlamalı
            </p>
          </div>

          <Button type="submit" disabled={submitting} variant="accent">
            {submitting ? "Gönderiliyor…" : "Talebi gönder"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
