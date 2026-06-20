import { redirect } from "next/navigation";

/**
 * /app/interests → /app/clusters kalıcı yönlendirme (Faz 4 Dilim 2).
 *
 * Eski "İlgi Alanların" (örtük message_clusters görünümü) yeni "Kümelerim"
 * (açık abonelik) ile MÜKERRERDİ. Küme-merkezli vizyonda açık abonelik kanonik;
 * araştırma artık anlık abone ediyor (stream-end auto_subscribe) → Kümelerim
 * dolu. Eski bookmark/derin-link 404 olmasın diye redirect (sayfa silinmedi).
 */
export default function InterestsRedirect() {
  redirect("/app/clusters");
}
