export const metadata = {
  title: "Gizlilik Politikası | Nodrat",
};

export default function PrivacyPage() {
  return (
    <div>
      <h1>Gizlilik Politikası</h1>
      <p className="text-sm text-muted-foreground">
        Son güncelleme: 2 Mayıs 2026 (taslak v1.0)
      </p>

      <h2>1. Veri sorumlusu</h2>
      <p>
        Nodrat, kişisel verilerinizi 6698 sayılı KVKK kapsamında işler. Veri
        sorumlusu temas: <a href="mailto:dpo@nodrat.com">dpo@nodrat.com</a>.
      </p>

      <h2>2. Topladığımız veriler</h2>
      <ul>
        <li><strong>Hesap:</strong> e-posta, ad-soyad (opsiyonel), şifre hash'i</li>
        <li>
          <strong>Kullanım:</strong> üretim istekleri, üretilen içerikler, kota
          kayıtları, IP adresi, user-agent
        </li>
        <li>
          <strong>Çerezler:</strong> oturum + tercih çerezleri (
          <a href="/legal/cookies">Çerez Politikası</a>)
        </li>
        <li>
          <strong>Faturalandırma (Faz 6):</strong> ödeme bilgileri Iyzico/Stripe
          ile işlenir, Nodrat sadece son 4 hane + provider token saklar.
        </li>
      </ul>

      <h2>3. İşleme amaçları + hukuki dayanak (KVKK md.5)</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b">
            <th className="py-2 text-left">Amaç</th>
            <th className="py-2 text-left">Hukuki dayanak</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-b">
            <td className="py-2">Hesap oluşturma + erişim</td>
            <td className="py-2">Sözleşmenin ifası (md.5/2-c)</td>
          </tr>
          <tr className="border-b">
            <td className="py-2">İçerik üretimi (LLM)</td>
            <td className="py-2">Açık rıza (md.5/1) + meşru menfaat (md.5/2-f)</td>
          </tr>
          <tr className="border-b">
            <td className="py-2">Kota + faturalandırma</td>
            <td className="py-2">Sözleşmenin ifası + yasal yükümlülük</td>
          </tr>
          <tr className="border-b">
            <td className="py-2">Yurt dışı LLM transfer</td>
            <td className="py-2">Açık rıza (md.9) + standart sözleşme</td>
          </tr>
          <tr>
            <td className="py-2">Pazarlama</td>
            <td className="py-2">Açık rıza (opsiyonel)</td>
          </tr>
        </tbody>
      </table>

      <h2>4. Aktarımlar</h2>
      <p>
        İçerik üretimi için NVIDIA NIM (DeepSeek V3 dahil) ve diğer LLM
        sağlayıcılarına KVKK md.9 kapsamında <strong>PII redact edilmiş</strong>{" "}
        veriler gönderilir. Kullanıcı email/IP/hesap ID'si LLM'e gitmez.
      </p>

      <h2>5. Saklama süreleri</h2>
      <ul>
        <li>Hesap verileri: hesap silinene kadar + 1 yıl arşiv</li>
        <li>Kullanım kayıtları: 12 ay (KVKK gereği)</li>
        <li>Üretim içerikleri: kullanıcı silmediği sürece</li>
        <li>Audit log: 5 yıl (yasal zorunluluk)</li>
      </ul>

      <h2>6. Haklarınız (KVKK md.11)</h2>
      <p>
        Erişim, düzeltme, silme, unutulma, taşınabilirlik, otomatik karara itiraz
        haklarınızı{" "}
        <a href="/legal/privacy-request">KVKK Başvuru formu</a>'ndan kullanabilirsiniz.
        SLA: triaj 24 saat, yanıtlama 30 gün (KVKK gereği).
      </p>

      <h2>7. Güvenlik önlemleri</h2>
      <ul>
        <li>Şifreler Argon2id ile hash'lenir</li>
        <li>JWT 15 dk access + 30 gün refresh + rotation</li>
        <li>TLS 1.3 zorunlu</li>
        <li>PII otomatik redaction LLM çağrıları öncesi</li>
        <li>Düzenli güvenlik denetimleri (yıllık)</li>
      </ul>

      <h2>8. İletişim</h2>
      <p>
        Veri Koruma Sorumlusu (DPO):{" "}
        <a href="mailto:dpo@nodrat.com">dpo@nodrat.com</a> · KVKK başvuruları:{" "}
        <a href="/legal/privacy-request">privacy-request</a>.
      </p>
    </div>
  );
}
