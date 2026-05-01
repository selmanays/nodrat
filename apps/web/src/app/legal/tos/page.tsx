export const metadata = {
  title: "Kullanım Şartları | Nodrat",
};

export default function ToSPage() {
  return (
    <div>
      <h1>Kullanım Şartları</h1>
      <p className="text-sm text-muted-foreground">
        Son güncelleme: 2 Mayıs 2026 (taslak v1.0)
      </p>

      <h2>1. Hizmet kapsamı</h2>
      <p>
        <strong>Nodrat haber kaynağı değildir.</strong> Nodrat, kamuya açık
        kaynaklara dayalı olarak Türkçe gündem için içerik üretim ve doğrulama
        destek aracıdır. Çıktıları editör gözden geçirmeden yayınlanmamalıdır.
      </p>

      <h2>2. Hesap ve yaş gerekliliği</h2>
      <p>
        Nodrat'a kayıt olmak için 18 yaşından büyük olmanız gerekir. KVKK md.6
        kapsamında küçükler için ayrı veli onayı gerekir; bu MVP'de sunulmamaktadır.
      </p>

      <h2>3. Yasak kullanımlar</h2>
      <ul>
        <li>İçerik manipülasyonu, kasıtlı yanlış bilgi üretimi</li>
        <li>Hakaret, taciz, tehdit, kişisel hak ihlali</li>
        <li>Telif hakkı (FSEK) ihlali — 25 kelimeden uzun direct quote yasak</li>
        <li>Robots.txt ihlali girişimi (zaten teknik düzeyde engellenir)</li>
        <li>Otomatik scraping / API abuse — kotalar dışına çıkma</li>
      </ul>

      <h2>4. Veri ve kaynak kullanımı</h2>
      <p>
        Nodrat scraping ile elde ettiği haberleri internal RAG katmanında saklar.
        <strong> Tam haber metni son kullanıcıya gösterilmez</strong> — sadece
        özet, ana noktalar ve kaynak referansı sunulur. Yayıncı şikayetleri için{" "}
        <a href="/legal/copyright">Telif İhlali</a> formunu kullanın.
      </p>

      <h2>5. LLM çıktıları ve sorumluluk</h2>
      <p>
        Nodrat çıktıları LLM tarafından üretilir. Halüsinasyon riskine karşı 3
        katmanlı koruma vardır:
      </p>
      <ul>
        <li>Veri yetersizliğinde içerik üretmeyi reddetme</li>
        <li>Source-grounded prompt + entity verification</li>
        <li>Kullanıcıya halüsinasyon raporu butonu</li>
      </ul>
      <p>
        Yayınlanan içeriklerin doğruluğundan{" "}
        <strong>kullanıcı sorumludur</strong>. Editör gözden geçirme zorunludur.
      </p>

      <h2>6. Ücretlendirme ve iade</h2>
      <p>
        Pro/Agency planlarında 14 gün koşulsuz iade hakkı saklıdır. KDV dahildir
        (Türkiye %20). Detaylar Faturalandırma sayfasında.
      </p>

      <h2>7. Hesap sonlandırma</h2>
      <p>
        Hesabınızı{" "}
        <a href="/app/settings">/app/settings</a> üzerinden silebilir
        veya KVKK md.11 kapsamında veri silme talebinde bulunabilirsiniz (
        <a href="/legal/privacy-request">/legal/privacy-request</a>).
      </p>

      <h2>8. Uygulanacak hukuk</h2>
      <p>
        Bu şartlar Türkiye Cumhuriyeti yasalarına tabidir. Anlaşmazlıklarda
        İstanbul (Çağlayan) Mahkemeleri yetkilidir.
      </p>

      <h2>9. Değişiklikler</h2>
      <p>
        Şartlar güncellenirse 30 gün önceden e-posta ile bildirilir. Kabul
        edilmezse hesabı silebilirsiniz.
      </p>

      <p className="text-sm text-muted-foreground border-t pt-4">
        İletişim:{" "}
        <a href="mailto:legal@nodrat.com" className="text-brand-700 hover:underline">
          legal@nodrat.com
        </a>
      </p>
    </div>
  );
}
