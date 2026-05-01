import { TakedownForm } from "@/components/legal/takedown-form";

export const metadata = {
  title: "Kötüye Kullanım Bildir | Nodrat",
};

export default function AbusePage() {
  return (
    <div>
      <h1>Kötüye Kullanım Bildir</h1>
      <p>
        Nodrat üzerinde spam, hakaret, taciz, dolandırıcılık veya benzeri kötüye
        kullanım fark ettiyseniz bu form ile bildirimde bulunabilirsiniz.
        Bildirimler 24 saat içinde triaj ekibimiz tarafından incelenir.
      </p>
      <p className="text-sm text-muted-foreground">
        FSEK telif şikayeti için{" "}
        <a href="/legal/copyright">Telif İhlali</a>, KVKK md.11 başvurusu için{" "}
        <a href="/legal/privacy-request">KVKK Başvuru</a>, 5651 sayılı kanun
        kaldırma talebi için <a href="/legal/takedown">Kaldırma Talebi</a>{" "}
        formunu kullanın.
      </p>
      <TakedownForm
        endpoint="abuse"
        title="Kötüye kullanım formu"
        description="Şikayetinize konu içeriği detaylı açıklayın. 24 saat triaj SLA'sı."
        authorityHint="Örn. mağdur / üçüncü taraf gözlemci / kurumsal yetkili"
      />
    </div>
  );
}
