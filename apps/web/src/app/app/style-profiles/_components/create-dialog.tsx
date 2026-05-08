"use client";

import { useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import { Textarea } from "@/components/ui/textarea";
import { ApiException } from "@/lib/api";
import {
  createStyleProfile,
  isPaywallRequired,
  isSlotFull,
  type ProfileCreateRequest,
} from "@/lib/style-profiles-api";

interface CreateProfileDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

const MIN_SAMPLE_LEN = 20;
const MIN_SAMPLES = 3;
const MAX_SAMPLE_CHARS = 4000;

interface SampleDraft {
  text: string;
  source_url: string;
}

const emptySample = (): SampleDraft => ({ text: "", source_url: "" });

export function CreateProfileDialog({
  open,
  onClose,
  onCreated,
}: CreateProfileDialogProps) {
  const [name, setName] = useState("");
  const [sourceType, setSourceType] = useState<
    "manual" | "csv_import" | "public_account"
  >("manual");
  const [samples, setSamples] = useState<SampleDraft[]>([
    emptySample(),
    emptySample(),
    emptySample(),
  ]);
  const [submitting, setSubmitting] = useState(false);

  function reset() {
    setName("");
    setSourceType("manual");
    setSamples([emptySample(), emptySample(), emptySample()]);
  }

  const validSampleCount = samples.filter(
    (s) => s.text.trim().length >= MIN_SAMPLE_LEN,
  ).length;

  async function handleSubmit() {
    const trimmedName = name.trim();
    if (!trimmedName) {
      toast.error("Profil adı gerekli");
      return;
    }
    if (validSampleCount < MIN_SAMPLES) {
      toast.error(
        `En az ${MIN_SAMPLES} adet 20+ karakterli örnek metin girin`,
      );
      return;
    }

    const cleanSamples = samples
      .map((s) => ({
        text: s.text.trim(),
        source_url: s.source_url.trim() || null,
      }))
      .filter((s) => s.text.length >= MIN_SAMPLE_LEN);

    const payload: ProfileCreateRequest = {
      name: trimmedName,
      source_type: sourceType,
      samples: cleanSamples,
    };

    setSubmitting(true);
    try {
      await createStyleProfile(payload);
      toast.success("Profil oluşturuldu, analiz başlatıldı");
      reset();
      onCreated();
    } catch (err) {
      if (isPaywallRequired(err)) {
        toast.error("Stil profili için Pro tier gerekiyor");
      } else if (isSlotFull(err)) {
        toast.error("Plan kotanız dolu — eski profili silin veya yükseltin");
      } else {
        toast.error((err as ApiException).message || "Oluşturulamadı");
      }
    } finally {
      setSubmitting(false);
    }
  }

  function handleClose() {
    if (submitting) return;
    reset();
    onClose();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) handleClose();
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Yeni stil profili</DialogTitle>
          <DialogDescription>
            En az {MIN_SAMPLES} adet 20+ karakterli örnek metin ekleyin. Sistem
            ortak yazı özelliklerini çıkararak rules_json üretir.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="grid gap-2">
            <Label htmlFor="profile-name">Profil adı</Label>
            <Input
              id="profile-name"
              placeholder="Örn: Köşe yazımın tonu"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={submitting}
              maxLength={180}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="source-type">Kaynak türü</Label>
            <Select
              value={sourceType}
              onValueChange={(v) =>
                setSourceType(v as typeof sourceType)
              }
              disabled={submitting}
            >
              <SelectTrigger id="source-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="manual">
                  Kendi yazılarımdan örnek
                </SelectItem>
                <SelectItem value="public_account">
                  Beğendiğim açık bir hesabın yazıları
                </SelectItem>
                <SelectItem value="csv_import">CSV import</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label>Örnek metinler</Label>
              <span className="text-xs text-muted-foreground">
                {validSampleCount} / {MIN_SAMPLES} geçerli
              </span>
            </div>
            <div className="flex flex-col gap-3">
              {samples.map((sample, idx) => (
                <div
                  key={idx}
                  className="flex flex-col gap-2 rounded-md border bg-card p-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-muted-foreground">
                      Örnek {idx + 1}
                    </span>
                    {samples.length > MIN_SAMPLES && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={submitting}
                        onClick={() =>
                          setSamples((prev) =>
                            prev.filter((_, i) => i !== idx),
                          )
                        }
                      >
                        <Trash2 className="size-3" />
                      </Button>
                    )}
                  </div>
                  <Textarea
                    rows={4}
                    value={sample.text}
                    placeholder={`En az ${MIN_SAMPLE_LEN} karakter — yazı örneği`}
                    onChange={(e) =>
                      setSamples((prev) => {
                        const next = [...prev];
                        next[idx] = { ...next[idx], text: e.target.value };
                        return next;
                      })
                    }
                    disabled={submitting}
                    maxLength={MAX_SAMPLE_CHARS}
                    className="font-mono text-xs"
                  />
                  <Input
                    type="url"
                    placeholder="Kaynak URL (opsiyonel)"
                    value={sample.source_url}
                    onChange={(e) =>
                      setSamples((prev) => {
                        const next = [...prev];
                        next[idx] = {
                          ...next[idx],
                          source_url: e.target.value,
                        };
                        return next;
                      })
                    }
                    disabled={submitting}
                    maxLength={2000}
                    className="h-8 text-xs"
                  />
                  <span className="text-xs text-muted-foreground">
                    {sample.text.length} / {MAX_SAMPLE_CHARS} karakter
                  </span>
                </div>
              ))}

              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={submitting || samples.length >= 50}
                onClick={() =>
                  setSamples((prev) => [...prev, emptySample()])
                }
                className="self-start"
              >
                <Plus className="mr-1 size-3" />
                Örnek ekle
              </Button>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={submitting}
            onClick={handleClose}
          >
            İptal
          </Button>
          <Button
            type="button"
            disabled={submitting || validSampleCount < MIN_SAMPLES}
            onClick={() => void handleSubmit()}
          >
            {submitting && (
              <Loader2 className="mr-1 size-4 animate-spin" />
            )}
            Oluştur ve analiz et
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
