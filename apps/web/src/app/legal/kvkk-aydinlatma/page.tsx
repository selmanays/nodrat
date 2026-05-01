export const metadata = {
  title: "KVKK Aydınlatma Metni | Nodrat",
};

export default function KvkkPage() {
  return (
    <div>
      <h1>KVKK Aydınlatma Metni</h1>
      <p className="text-sm text-muted-foreground">
        6698 sayılı Kanun md.10 — Son güncelleme: 2 Mayıs 2026 (taslak v1.0)
      </p>

      <h2>Veri sorumlusu</h2>
      <p>
        Nodrat platformunu işleten {"<şirket adı tescil sonrası buraya>"}.
        İletişim: <a href="mailto:dpo@nodrat.com">dpo@nodrat.com</a> · adres:
        İstanbul, Türkiye.
      </p>

      <h2>Hangi kişisel verileri işliyoruz?</h2>
      <ul>
        <li>Kimlik: e-posta (zorunlu), ad-soyad (opsiyonel)</li>
        <li>İletişim: e-posta</li>
        <li>İşlem güvenliği: IP adresi, user-agent, oturum kayıtları</li>
        <li>
          Kullanım: ürettiğiniz içerikler, üretim istekleri, kota tüketimi,
          maliyet kayıtları
        </li>
      </ul>

      <h2>Hangi amaçlarla işliyoruz?</h2>
      <ol>
        <li>Hizmet sunumu (sözleşmenin ifası — md.5/2-c)</li>
        <li>Hesap güvenliği + erişim kontrolü</li>
        <li>İçerik üretiminde halüsinasyon koruması ve denetim</li>
        <li>Yasal yükümlülükler (5651, 6493, vergi mevzuatı)</li>
        <li>İstatistik + ürün geliştirme (anonimleştirilmiş)</li>
      </ol>

      <h2>Yurt dışı transfer (KVKK md.9)</h2>
      <p>
        İçerik üretimi için aşağıdaki yurt dışı sağlayıcılara{" "}
        <strong>PII redact edilmiş</strong> veriler gönderilir:
      </p>
      <ul>
        <li>NVIDIA NIM (ABD) — DeepSeek V3, embedding modelleri</li>
        <li>Anthropic (ABD) — Claude (Pro/Agency tier'da)</li>
      </ul>
      <p>
        Aktarım için <strong>açık rızanız</strong> alınır (kayıt formundaki ayrı
        checkbox). Standart sözleşme hükümleri (SCC) uygulanır.
      </p>

      <h2>Kimlerle paylaşılır?</h2>
      <ul>
        <li>Yurt içi: ödeme sağlayıcı (Iyzico — Faz 6), hosting (Türkiye/AB)</li>
        <li>Yurt dışı: yukarıdaki LLM sağlayıcıları (sadece redact edilmiş veri)</li>
        <li>Yetkili kamu kurumları (yasal talep halinde)</li>
      </ul>

      <h2>Toplama yöntemi ve hukuki sebepler</h2>
      <ul>
        <li>Doğrudan sizden — kayıt + kullanım sırasında</li>
        <li>Otomatik — log + telemetri</li>
      </ul>

      <h2>Haklarınız (md.11)</h2>
      <p>
        Verilerinizin işlenip işlenmediğini öğrenme, bilgi talep etme, eksik /
        yanlış işlenmişse düzeltme, silme veya yok etme talebinde bulunma,
        aktarımları öğrenme, otomatik karara itiraz, zarar tazmini.
      </p>

      <p>
        Başvurularınız için:{" "}
        <a href="/legal/privacy-request">KVKK md.11 Başvuru formu</a> veya{" "}
        <a href="mailto:dpo@nodrat.com">dpo@nodrat.com</a>.
      </p>

      <h2>Saklama süresi</h2>
      <p>
        Aktif hesap süresi + 1 yıl arşiv; yasal zorunluluklar için 5 yıl audit
        log.
      </p>

      <p className="text-sm text-muted-foreground border-t pt-4">
        Bu metin avukat onayı sonrası nihai halini alacaktır. Önerileriniz için:{" "}
        <a href="mailto:dpo@nodrat.com">dpo@nodrat.com</a>.
      </p>
    </div>
  );
}
