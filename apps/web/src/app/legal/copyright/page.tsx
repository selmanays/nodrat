import { TakedownForm } from "@/components/legal/takedown-form";

export const metadata = {
  title: "Telif Hakkı (FSEK) İhlali | Nodrat",
};

export default function CopyrightPage() {
  return (
    <div>
      <h1>Telif Hakkı (FSEK) İhlali Bildirimi</h1>
      <p>
        5846 sayılı Fikir ve Sanat Eserleri Kanunu (FSEK) kapsamında, Nodrat
        üzerinde gösterilen içerikte telif hakkınızın ihlal edildiğini
        düşünüyorsanız bu form ile başvurabilirsiniz.
      </p>
      <p>
        <strong>Nodrat'ın FSEK politikası:</strong>
      </p>
      <ul>
        <li>
          Tam haber metnini son kullanıcıya göstermeyiz; sadece kaynak
          referansları ve <strong>25 kelimeyi aşmayan</strong> doğrudan alıntı
          kullanırız.
        </li>
        <li>Başvurunuzda telif sahipliğinizi kanıtlayan belge sunmanız beklenir.</li>
        <li>
          Doğrulanmış telif ihlali iddiaları için 7-30 gün içinde aksiyon
          alınır (kaldırma / kaynak güncelleme / atıf düzeltme).
        </li>
      </ul>
      <TakedownForm
        endpoint="copyright"
        title="FSEK Telif ihlali formu"
        description="Telif sahipliğinizi belirten kanıt URL'leri ekleyin. Triaj 24 saat."
        authorityHint="Örn. eser sahibi / yayıncı / vekil"
        requireSubjectUrl
      />
    </div>
  );
}
