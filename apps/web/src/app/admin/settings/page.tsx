"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { SETTINGS_GROUPS } from "@/lib/settings-groups";

export default function AdminSettingsIndexPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace(`/admin/settings/${SETTINGS_GROUPS[0].slug}`);
  }, [router]);
  return null;
}
