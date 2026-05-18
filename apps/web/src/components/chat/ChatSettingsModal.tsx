"use client";

import { Settings2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  listStyleProfiles,
  type StyleProfileItem,
} from "@/lib/style-profiles-api";

/**
 * ChatSettings — sohbet için runtime parametre ayarları.
 *
 * Mevcut form modu parametreleri (output_type, tone, length, max_posts,
 * style_profile_id, show_sources) sohbet'e taşındı. localStorage
 * (global default + per-conversation override) ile saklanır.
 */
export interface ChatSettings {
  output_type: string;          // x_post | x_thread | summary | analysis | headline | "" (otomatik)
  tone: string;                 // tarafsız | eleştirel | mizahi | kurumsal | resmi | ""
  length: string;               // short | medium | long | ""
  max_posts: number | null;     // 1-10 veya null (otomatik)
  style_profile_id: string | null;
  show_sources: boolean;
}

export const DEFAULT_CHAT_SETTINGS: ChatSettings = {
  output_type: "",
  tone: "",
  length: "",
  max_posts: null,
  style_profile_id: null,
  show_sources: true,
};

const STORAGE_KEY_GLOBAL = "chat-settings-default";
const STORAGE_KEY_CONV_PREFIX = "chat-settings-conv-";

export function loadChatSettings(conversationId?: string): ChatSettings {
  if (typeof window === "undefined") return DEFAULT_CHAT_SETTINGS;
  try {
    const key = conversationId
      ? `${STORAGE_KEY_CONV_PREFIX}${conversationId}`
      : STORAGE_KEY_GLOBAL;
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      // Conversation-specific yoksa global default'a düş
      if (conversationId) return loadChatSettings();
      return DEFAULT_CHAT_SETTINGS;
    }
    return { ...DEFAULT_CHAT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_CHAT_SETTINGS;
  }
}

export function saveChatSettings(
  settings: ChatSettings,
  conversationId?: string,
): void {
  if (typeof window === "undefined") return;
  try {
    const key = conversationId
      ? `${STORAGE_KEY_CONV_PREFIX}${conversationId}`
      : STORAGE_KEY_GLOBAL;
    window.localStorage.setItem(key, JSON.stringify(settings));
  } catch {
    /* localStorage disabled */
  }
}

// ============================================================================
// Component
// ============================================================================

export interface ChatSettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conversationId?: string;
  onSaved?: (settings: ChatSettings) => void;
}

export function ChatSettingsModal({
  open,
  onOpenChange,
  conversationId,
  onSaved,
}: ChatSettingsModalProps) {
  const [settings, setSettings] = useState<ChatSettings>(DEFAULT_CHAT_SETTINGS);
  const [profiles, setProfiles] = useState<StyleProfileItem[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(false);
  const [proGated, setProGated] = useState(false);

  // Modal açıldığında settings yükle
  useEffect(() => {
    if (!open) return;
    setSettings(loadChatSettings(conversationId));
  }, [open, conversationId]);

  // Style profiles fetch (Pro+ paywall)
  const fetchProfiles = useCallback(async () => {
    setProfilesLoading(true);
    try {
      const list = await listStyleProfiles();
      setProfiles(list.data.filter((p) => p.status === "ready"));
      setProGated(!list.quota.style_profiles_enabled);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.toLowerCase().includes("pro") || msg.includes("402")) {
        setProGated(true);
      }
      setProfiles([]);
    } finally {
      setProfilesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) fetchProfiles();
  }, [open, fetchProfiles]);

  const handleSave = () => {
    saveChatSettings(settings, conversationId);
    onSaved?.(settings);
    onOpenChange(false);
  };

  const handleReset = () => {
    setSettings(DEFAULT_CHAT_SETTINGS);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings2 className="size-4" />
            Araştırma ayarları
          </DialogTitle>
          <DialogDescription>
            {conversationId
              ? "Bu araştırmaya özel parametreler — varsayılan ayarları geçersiz kılar."
              : "Yeni araştırmalar için varsayılan parametreler."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <Field label="Çıktı türü" hint="Otomatik = planner karar verir">
            <Select
              value={settings.output_type || "_auto"}
              onValueChange={(v) =>
                setSettings({ ...settings, output_type: v === "_auto" ? "" : v })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="_auto">Otomatik</SelectItem>
                <SelectItem value="x_post">X Post</SelectItem>
                <SelectItem value="x_thread">X Thread</SelectItem>
                <SelectItem value="summary">Özet</SelectItem>
                <SelectItem value="analysis">Analiz</SelectItem>
                <SelectItem value="headline">Başlık</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Field label="Ton">
            <Select
              value={settings.tone || "_auto"}
              onValueChange={(v) =>
                setSettings({ ...settings, tone: v === "_auto" ? "" : v })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="_auto">Otomatik</SelectItem>
                <SelectItem value="tarafsız">Tarafsız</SelectItem>
                <SelectItem value="eleştirel">Eleştirel</SelectItem>
                <SelectItem value="mizahi">Mizahi</SelectItem>
                <SelectItem value="kurumsal">Kurumsal</SelectItem>
                <SelectItem value="resmi">Resmi</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Field label="Uzunluk">
            <Select
              value={settings.length || "_auto"}
              onValueChange={(v) =>
                setSettings({ ...settings, length: v === "_auto" ? "" : v })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="_auto">Otomatik</SelectItem>
                <SelectItem value="short">Kısa</SelectItem>
                <SelectItem value="medium">Orta</SelectItem>
                <SelectItem value="long">Uzun</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Field label="Paylaşım adedi" hint="X Post / X Thread için">
            <Select
              value={settings.max_posts == null ? "_auto" : String(settings.max_posts)}
              onValueChange={(v) =>
                setSettings({
                  ...settings,
                  max_posts: v === "_auto" ? null : Number(v),
                })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="_auto">Otomatik</SelectItem>
                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field label="Stil profili" hint="Pro+ üyelik gerek">
            {proGated ? (
              <div className="rounded-md border border-dashed border-border bg-muted/30 p-2 text-xs text-muted-foreground">
                Stil profilleri{" "}
                <Link
                  href="/app/billing"
                  className="underline hover:text-foreground"
                >
                  Pro üyelikte
                </Link>{" "}
                kullanılabilir.
              </div>
            ) : (
              <Select
                value={settings.style_profile_id || "_none"}
                onValueChange={(v) =>
                  setSettings({
                    ...settings,
                    style_profile_id: v === "_none" ? null : v,
                  })
                }
                disabled={profilesLoading}
              >
                <SelectTrigger>
                  <SelectValue
                    placeholder={profilesLoading ? "Yükleniyor..." : "Profil seç"}
                  />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">Yok</SelectItem>
                  {profiles.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </Field>

          <div className="flex items-center justify-between rounded-md border border-border bg-card/40 px-3 py-2">
            <div>
              <Label className="text-sm">Kaynakları göster</Label>
              <p className="text-xs text-muted-foreground">
                Cevap altında kaynak listesi (default açık)
              </p>
            </div>
            <Switch
              checked={settings.show_sources}
              onCheckedChange={(v) =>
                setSettings({ ...settings, show_sources: v })
              }
            />
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="ghost" onClick={handleReset}>
            Sıfırla
          </Button>
          <div className="flex-1" />
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Vazgeç
          </Button>
          <Button onClick={handleSave}>Kaydet</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-sm">
        {label}
        {hint && <span className="ml-1.5 text-xs font-normal text-muted-foreground">— {hint}</span>}
      </Label>
      {children}
    </div>
  );
}
