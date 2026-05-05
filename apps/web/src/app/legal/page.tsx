import Link from "next/link";

export const metadata = {
  title: "Yasal — Nodrat",
};

export default function LegalIndexPage() {
  return (
    <div>
      <h1>Yasal</h1>
      <p>
        Nodrat platformuyla ilgili politikalar, yasal şartlar ve talep formları.
      </p>

      <h2>Politikalar</h2>
      <ul>
        <li><Link href="/legal/tos">Kullanım Şartları</Link></li>
        <li><Link href="/legal/privacy">Gizlilik Politikası</Link></li>
        <li><Link href="/legal/kvkk-aydinlatma">KVKK Aydınlatma Metni</Link></li>
        <li><Link href="/legal/cookies">Çerez Politikası</Link></li>
        <li><Link href="/legal/scraping">Tarama Politikası (Yayıncılar)</Link></li>
      </ul>

      <h2>Talep formları</h2>
      <ul>
        <li><Link href="/legal/abuse">Kötüye Kullanım Bildirimi</Link></li>
        <li><Link href="/legal/takedown">5651 Kaldırma Talebi</Link></li>
        <li><Link href="/legal/copyright">FSEK Telif İhlali</Link></li>
        <li><Link href="/legal/privacy-request">KVKK md.11 Başvurusu</Link></li>
      </ul>

      <p className="text-sm text-muted-foreground border-t pt-4">
        Genel yasal sorular:{" "}
        <a href="mailto:legal@nodrat.com" className="text-primary hover:underline">
          legal@nodrat.com
        </a>{" "}
        · DPO:{" "}
        <a href="mailto:dpo@nodrat.com" className="text-primary hover:underline">
          dpo@nodrat.com
        </a>
      </p>
    </div>
  );
}
