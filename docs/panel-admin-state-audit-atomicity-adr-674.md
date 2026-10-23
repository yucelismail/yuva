# Yuva #674 — Panel state + audit JSONL atomiklik ADR'si

**Karar:** Mevcut `/api/sorumlu` ve `/api/bas-denetci` davranışı iki ayrı
kalıcılık adımıdır; ortak kilit bunları atomik yapmaz. Mevcut akış için
**cross-file transaction veya exactly-once audit garantisi yoktur**. Gelecekteki
doğru yön, durum mutasyonu + idempotency receipt + audit outbox olayını tek
`durum.json` snapshot commit'ine almak, sonra audit JSONL'yi exact event ID ile
uzlaştırmalı teslim etmektir. Bu, uygulama izni veya live rollout kararı
değildir; önce data-contract uyumu, bounded retention ve acceptance fixture'ı
karara bağlanmalıdır.

## Bugünkü çağrı ve kilit sınırı

Her iki API şu sırayı yürütür:

```text
with panel KILIT (process-local RLock), YUVA_DIR/.kilit (flock, max 10 s):
    durum_oku()
    in-memory state mutation
    durum_yaz()                    # durum.json temp + file fsync + replace + dir fsync
    admin_mutasyon_audit_ekle()    # mesaj.jsonl append; başka kalıcı işlem
```

`mesaj_ekle()`/`ekle()` aynı thread'deki nested `.kilit` edinimini reentrant
derinlik sayacıyla atlar. Böylece iki adım arasında başka **uyumlu** panel/CLI
yazımı girmez. `KILIT` yalnız panel process/thread koordinasyonudur; süreçler
arası koordinasyon `.kilit`'tir. Kilit tek bir kritik bölge sağlar, iki pathname
üzerinde atomic commit sağlamaz. `INSTALL_ROOT` veya auth store kilitleri bu
data-root transaction'ın yerine geçmez.

`durum_yaz()` JSON dosyasında temp write, file `fsync`, `os.replace` ve parent
directory `fsync` yapar. Replace sonrası directory `fsync` hatasında yeni
state görünür olabilir ama dayanıklılığı belirsizdir. `ekle()` JSONL satırını
`O_APPEND` ile tüm byte'lar yazılana kadar yazar ve fd'yi kapatır; bu yolda
`fsync` çağrısı yoktur. Dolayısıyla handler `200` dönmüş olsa bile audit satırı
güç kaybına karşı durable kabul edilemez.

`api_sorumlu()` önce `durum.json`'a tek ilişkiyi yazar, ardından audit'e
`before/after` ekler. `api_bas_denetci()` önce state'i yazar; baş denetçi
değişimi başka denetçilerin sorumluluk bağlarını taşıyabilir ve hedefin kendi
bağını kaldırabilir. Sonraki audit satırı yalnız eski/yeni baş denetçi ID'sini
taşır; bu çoklu kenar değişikliklerinin tam delta'sı değildir. Audit append
hatasında iki endpoint `503`, `mutasyon_kaydedildi=true`,
`audit_durumu=belirsiz` döndürür. Bu dürüst bir kısmi-commit belirtimidir ama
ne append'i geri alır ne de sonraki retry'ı idempotent yapar.

## Arıza / yeniden deneme matrisi

| Kesinti noktası | Olası kalıcı durum | Güvenli sonuç ve retry sınırı |
|---|---|---|
| JSON doğrulaması veya state yazımı replace öncesi hata | `durum.json` eski; audit başlamadı | Mutation yok ancak yapılandırılmış receipt yok. Mevcut route sıradan `500` üretebilir. |
| `durum.json` replace oldu, directory `fsync` hata verdi | Yeni state görünür olabilir; crash sonrası durability bilinmez; audit çağrısı yapılmamıştır | **Commit unknown.** Handler'ın genel `500` mesajı “dosya değiştirilmedi” diyebilir; bu post-replace durumunu doğru tarif etmeyebilir. Yeni işlem açıp kör retry yapmak güvenli değil. |
| State kesin yazıldı, audit append öncesi süreç çöktü | Mutation var; audit yok | Kalıcı audit boşluğu. Aynı istek tekrar edilirse state tekrar yazılır ve audit için yeni random event ID üretilebilir. |
| Audit append kısmi/error | Mutation var; JSONL'de hiç, tam veya kısmi satır olabilir | Mevcut `503` audit'i belirsiz olarak raporlar. Event ID request/receipt'te önceden sabitlenmediği için exact retry/readback sözleşmesi yok; bozuk tail mümkündür. |
| Audit satırı `write()` tamamlandı, `fsync` yok; sonra süreç/host durdu | Mutation durable olabilir; audit satırı görünür veya kayıp olabilir | API 200 yanıtı satırın kalıcılığını kanıtlamaz. |
| İki yazım tamamlandı, HTTP response kayboldu | Mutation ve audit şu an görünür; audit power-loss durability yine garanti değil | Client aynı isteği tekrar ederse stable operation ID/dedupe yokluğunda duplicate audit ve `durum.json.rev` artışı oluşabilir. |

## Seçenekler

| Seçenek | Sağladığı şey | Mevcut kilitlerle uyumu / maliyeti | Karar |
|---|---|---|---|
| A. İki ayrı yazım + açık `commit_unknown` | Durum ve audit hatalarının farklı olduğunu dürüstçe bildirir; kısa vadede mevcut formatı korur | Var olan `KILIT → .kilit` sırasını korur; receipt/readback yoksa bilinmeyen mutation'ı otomatik çözemez. Sadece doğru hata mesajı atomiklik sağlamaz. | Şimdiki davranışın geçici tanımı; audit zorunlu kullanım için kabul edilebilir transaction değil. |
| B. Audit'i önce append et, sonra state yaz | Audit satırını mutation'dan önce görünür yapar | State yazımı reddedilirse log gerçekte olmamış mutation'ı olmuş gibi gösterir; intent/commit protokolü eklenmezse yanıltıcıdır. | **Reddedildi.** |
| C. State ve audit JSONL'yi tek `.kilit` altında yazmaya devam et | Cooperative writer interleaving'ini engeller | Bugünkü kod zaten bunu yapıyor. Bir lock iki dosyaya atomik rename/append kazandırmaz; crash aralığını kapatmaz. | **Yetersiz; transaction diye sunulmayacak.** |
| D. State + receipt + audit outbox tek `durum.json` snapshot'ında; audit JSONL projection | Mutation sonucu ile “audit teslim bekliyor” niyetini bir atomik replace'te bağlar; aynı `operation_id` duplicate'ini çözer | Aynı panel/CLI `YUVA_DIR/.kilit` kapsamında snapshot edilir. Sonraki JSONL append exact event ID/body ile uzlaştırılır. Outbox count/byte cap, retention/tombstone, schema ve tüm writer'ların unknown alanı koruması gerekir. JSONL append için fdatasync/fsync ve append-unknown kuralı eklenmelidir. | **Önerilen hedef**, ancak compatibility, cap/retention kararı ve fixture geçmeden uygulanmamalı. |
| E. SQLite/başka transactional DB içinde state + audit | İki kayıt tek DB transaction olabilir | Mevcut `durum.json` okuyucuları, CLI/panel ve backup/restore zinciri için migration ve tek writer geçişi gerekir; aynı-UID/legacy writer'lar DB transaction'ını atlayabilir. | Alternatif gelecek mimari; bu dar görevde seçilmedi. |

## Önerilen hedef protokol (D)

1. İstemci her mantıksal admin mutasyonu için bir kez kararlı, yüksek
   entropili `operation_id` üretir ve aynı ID'yi timeout/response-loss retry'ında
   saklar. Server canonical işlem türü, hedef ve normalize edilmiş before/after
   delta'yı digest'e bağlar; operation receipt principal/auth scope'a da
   bağlanır. Her retry'da route authorization receipt lookup'tan önce yeniden
   uygulanır. `operation_id` principal veya yetki kanıtı değildir.
2. `KILIT → YUVA_DIR/.kilit` altında receipt lookup yapılır. Aynı ID + aynı
   digest önceki sonucu döndürür; mutation veya audit event'i ikinci kez
   üretilmez. Aynı ID + farklı digest `409 idempotency_conflict` olur.
3. Task outbox prototipindeki gibi, **aynı `durum.json` yeni snapshot'ında**
   state delta, receipt (`committed`/`commit_unknown` reconciliation bilgisi)
   ve tam audit event body + sabit `event_id`/`pending` durumu yazılır. `bas_denetci`
   değişiminin etkilediği her responsibility kenarı delta'ya dahil edilir.
4. Temp file write + file fsync + replace + parent directory fsync kesin
   olmadan `committed` raporlanmaz. Replace sonrası fsync hatası `commit_unknown`
   olur; worker/audit append bekler ve aynı operation ID readback'i gerekir.
   Receipt görünmesi tek başına directory durability kanıtı sayılmaz; recovery
   aynı snapshot'ı güvenli biçimde yeniden fsync edebilmeli veya operatör
   uzlaştırması istemelidir.
5. Audit dispatcher aynı `.kilit` protokolü altında full JSONL readback yapar.
   Tam bir exact `event_id` + exact expected body varsa delivered marker'ı
   snapshot'a yazar. ID farklı body ile varsa, ID birden fazlaysa, append/readback
   belirsizse veya tail bozuksa `delivery_unknown` olur; kör append yapılmaz.
   Append'in başarıyla durable sayılması için data fd `fsync`/`fdatasync` ve
   yeni dosyada gerekiyorsa parent directory `fsync` kabul ölçütüne girer.
6. API mutation sonucu ile audit teslimini ayırır: ör. `mutation=committed`,
   `audit=pending|delivered|delivery_unknown`. Audit zorunlu eşikse pending veya
   unknown sonuç “tamamlandı” olarak sunulmaz; ancak state commit'i de `rejected`
   diye yanlış sınıflandırılmaz. Poll/reconcile aynı operation/event ID'lerle
   yapılır.

## Önkoşullar ve açık kararlar

- `durum.json` içine outbox/receipt alanı eklemek data-contract değişikliğidir.
  Schema sürümü, unknown nested alan politikası, eski CLI/panel/backup/restore
  writer'larının davranışı ve gerçek rollback hedefleri önce kanıtlanmalı.
- Receipt ve outbox için count/byte limitleri, retention/tombstone süresi,
  eski ID retry penceresi, full JSONL readback maliyeti ve malformed-tail
  recovery kararı yok. Limit dolduğunda mutation fail-closed olmalı; otomatik
  eviction/retry yok.
- Current auth-off actor değeri unverified olabilir. Audit, `principal` varsa
  verified HMAC metadata'sını; yoksa `actor_id=null`/`local_unverified` trust
  değerini korumalı. Receipt/audit key'i actor authorization yerine geçmez.
- Mevcut `KILIT` process-local ve `.kilit` cross-process kilittir. Tüm state
  yazarları aynı inode/protokolü kullanmalı; kilidi tutarken blocking dış
  callback/network çağrısı yapılmamalı. Route-level idempotency dış writer veya
  legacy copy bypass'ını kapatmaz.
- `mesaj.jsonl` genel sohbet akışı ile admin audit event'lerini birlikte taşır.
  Audit projection'ın JSONL içinde aynı dosyada kalacağı mı, ayrı sınırlı audit
  store'a mı geçeceği; retention ve redaction ile beraber operatör kararı
  gerektirir.

## Karar ve sınır

Kısa vadede mevcut sıralama korunuyorsa UI/API “state commit oldu, audit
belirsiz” ayrımını muhafaza etmeli; `500` veya `503` tek başına “mutasyon olmadı”
diye yorumlanmamalı ve otomatik retry yapılmamalıdır. Bu, denetim bütünlüğü için
geçici risk kabulüdür; exactly-once değildir. Tercih edilen sonraki tasarım
receipt/outbox'tur, fakat #644 canonical-writer geçiş kapıları, data schema
uyumluluk/rollback, bounded retention ve fault fixture'ları kabul edilmeden
canlı route'lara uygulanmamalıdır.

Bu ADR kaynak incelemesidir. Kod, schema, API response, servis veya canlı data
değişikliği yapılmadı; arıza enjeksiyonu/test veya runtime doğrulaması
çalıştırılmadı.

## Kaynaklar

- `panel/server.py`: `api_sorumlu`, `api_bas_denetci`,
  `admin_mutasyon_audit_ekle`, `durum_yaz`, `yaz`, `ekle`, `dosya_kilidi`.
- [JSONL append güvenlik incelemesi #446](jsonl-append-security-review-446.md)
  — ortak lock ve append yazımının sınırları.
- [Görev mutasyonu hata matrisi #452](task-mutation-failure-matrix-452.md)
  — task outbox için commit/delivery unknown örnekleri; mevcut admin route
  garantisi değildir.
- [#644 canonical writer geçiş sözleşmesi](task-outbox-canonical-writer-transition-644.md)
  — schema, writer compatibility, receipt/outbox ve rollout kapıları.
- [#669 auth-off route risk incelemesi](panel-auth-off-mutation-route-review-669.md)
  — admin actor/auth-off ve non-atomic audit bulgusu.
