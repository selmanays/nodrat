import { redirect } from "next/navigation";

import { SETTINGS_GROUPS } from "@/lib/settings-groups";

export default function AdminSettingsIndexPage() {
  redirect(`/admin/settings/${SETTINGS_GROUPS[0].slug}`);
}
