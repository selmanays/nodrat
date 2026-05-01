import { TakedownForm } from "@/components/legal/takedown-form";

export const metadata = {
  title: "5651 Kaldırma Talebi | Nodrat",
};

export default function TakedownPage() {
  return (
    <div>
      <h1>5651 Sayılı Kanun — İçerik Kaldırma Talebi</h1>
      <p>
        İnternet ortamında yapılan yayınların düzenlenmesi ve bu yayınlar
        yoluyla işlenen suçlarla mücadele edilmesi hakkında kanun (5651)
        kapsamında, Nodrat üzerinde gösterilen bir içerikten dolayı kişilik
        haklarınızın ihlal edildiğini düşünüyorsanız bu form ile başvurabilirsiniz.
      </p>
      <p>
        <strong>Süreç:</strong>
      </p>
      <ol>
        <li>Triaj 24 saat içinde başlar.</li>
        <li>
          Şikayetiniz değerlendirilir; içerik 5651 m.9 kapsamında düşüyorsa 7 iş
          günü içinde aksiyon alınır.
        </li>
        <li>
          Sonuç (kaldırma / reddetme) tarafınıza e-posta ile bildirilir.
        </li>
        <li>
          İtiraz hakkınız için Sulh Ceza Hâkimliği'ne başvurabilirsiniz.
        </li>
      </ol>
      <TakedownForm
        endpoint="takedown"
        title="5651 Kaldırma talebi formu"
        description="Şikayet konusu URL ve gerekçe zorunlu. Triaj 24 saat, sonuçlanma 7 iş günü hedef."
        authorityHint="Örn. kişilik hakkı sahibi / vekil / yasal temsilci"
        requireSubjectUrl
      />
    </div>
  );
}
