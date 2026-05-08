"use client";

import Link from "next/link";
import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function ProAccessGate({ message }: { message: string }) {
  return (
    <Card className="border-primary/40 bg-primary/5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="size-5 text-primary" />
          Pro tier ile açılır
        </CardTitle>
        <CardDescription>{message}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <ul className="flex-1 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          <li>Kendi yazı stilinize özel içerik üretimi</li>
          <li>3 stil profili (Pro) / 10 stil profili (Agency)</li>
          <li>Premium model erişimi (Claude Haiku 4.5) Pro+ tier'da açık</li>
        </ul>
        <Button asChild>
          <Link href="/app/billing">Pro'ya yükselt</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
