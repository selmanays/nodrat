import { TakedownForm } from "@/components/legal/takedown-form";

export const metadata = {
  title: "KVKK md.11 Başvuru | Nodrat",
};

export default function PrivacyRequestPage() {
  return (
    <div>
      <h1>KVKK md.11 — İlgili Kişi Başvurusu</h1>
      <p>
        6698 sayılı Kişisel Verilerin Korunması Kanunu (KVKK) md.11 kapsamında,
        kişisel verileriniz hakkında aşağıdaki haklara sahipsiniz:
      </p>
      <ul>
        <li>Kişisel verinizin işlenip işlenmediğini öğrenme</li>
        <li>İşlenmişse buna ilişkin bilgi talep etme</li>
        <li>Verilerin yurt içi/yurt dışı aktarıldığı üçüncü kişileri bilme</li>
        <li>
          Eksik veya yanlış işlenmiş verilerin düzeltilmesini, silinmesini veya
          yok edilmesini (unutulma) isteme
        </li>
        <li>Verilerin tamamlanmış halinin üçüncü kişilere bildirilmesini isteme</li>
        <li>
          Otomatik işlemeye dayalı olarak aleyhe bir sonuç ortaya çıkmasına
          itiraz etme
        </li>
        <li>Zarara uğranılmışsa giderilmesini talep etme</li>
      </ul>
      <p>
        <strong>SLA:</strong> Triaj 24 saat. KVKK gereği yanıtlama süresi en fazla 30 gün
        (md.13/2). Talepleriniz çoğunlukla 7-14 gün içinde sonuçlandırılır.
      </p>
      <TakedownForm
        endpoint="privacy-request"
        title="KVKK md.11 başvuru formu"
        description="Hangi hakkı kullanmak istediğinizi açıklamada belirtin. Kimlik doğrulama gerekebilir."
        authorityHint="Örn. veri sahibi (ben) / vekil"
      />
    </div>
  );
}
