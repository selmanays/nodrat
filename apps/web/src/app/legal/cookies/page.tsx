export const metadata = {
  title: "Çerez Politikası | Nodrat",
};

export default function CookiesPage() {
  return (
    <div>
      <h1>Çerez Politikası</h1>
      <p className="text-sm text-muted-foreground">
        Son güncelleme: 2 Mayıs 2026 (taslak v1.0)
      </p>

      <h2>Çerezler nedir?</h2>
      <p>
        Çerezler, ziyaret ettiğiniz web siteleri tarafından tarayıcınıza
        kaydedilen küçük metin dosyalarıdır. Nodrat, hizmeti sunmak ve
        deneyiminizi iyileştirmek için aşağıdaki çerez tiplerini kullanır.
      </p>

      <h2>Kullandığımız çerezler</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b">
            <th className="py-2 text-left">Kategori</th>
            <th className="py-2 text-left">Amaç</th>
            <th className="py-2 text-left">Süre</th>
            <th className="py-2 text-left">Onay</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-b">
            <td className="py-2">Zorunlu</td>
            <td className="py-2">
              Oturum, güvenlik (CSRF), erişim token'ları
            </td>
            <td className="py-2">Oturum + 30 gün</td>
            <td className="py-2">Gerekli — onay aranmaz</td>
          </tr>
          <tr className="border-b">
            <td className="py-2">İşlevsel</td>
            <td className="py-2">Tema (light/dark), dil tercihi</td>
            <td className="py-2">12 ay</td>
            <td className="py-2">Onay gerekli</td>
          </tr>
          <tr className="border-b">
            <td className="py-2">Analitik</td>
            <td className="py-2">Anonim sayfa görüntüleme istatistikleri (Faz 2+)</td>
            <td className="py-2">12 ay</td>
            <td className="py-2">Onay gerekli</td>
          </tr>
          <tr>
            <td className="py-2">Pazarlama</td>
            <td className="py-2">
              Şu an kullanılmıyor — Faz 6+ ile gelirse açık onay alınacak.
            </td>
            <td className="py-2">—</td>
            <td className="py-2">Onay gerekli</td>
          </tr>
        </tbody>
      </table>

      <h2>Üçüncü taraf çerezleri</h2>
      <p>
        MVP-1'de üçüncü taraf çerezi kullanılmaz. Ödeme sağlayıcı{" "}
        <strong>Lemon Squeezy (Merchant of Record, Faz 6)</strong> hosted
        checkout ve customer portal akışlarında lemonsqueezy.com domain'i
        altında kendi çerezlerini kullanabilir.
      </p>

      <h2>Onay yönetimi</h2>
      <p>
        İlk ziyaretinizde çerez bandı (banner) gösterilir. Tercihinizi sayfa
        altındaki "Çerez tercihleri" linkinden istediğiniz zaman değiştirebilirsiniz.
      </p>
      <p>
        Tarayıcınızdan tüm çerezleri silmek için tarayıcı ayarlarını kullanın.
        Zorunlu çerezler silinirse oturumunuz kapanır.
      </p>

      <h2>Mobil cihazlar</h2>
      <p>
        Nodrat MVP-1'de mobil web olarak çalışır. Yerel uygulama Faz 7+
        roadmap'inde değil.
      </p>

      <p className="text-sm text-muted-foreground border-t pt-4">
        Çerez politikamız ile ilgili sorularınız için:{" "}
        <a href="mailto:dpo@nodrat.com">dpo@nodrat.com</a>.
      </p>
    </div>
  );
}
