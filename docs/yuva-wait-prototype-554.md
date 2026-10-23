# Yuva #554 — provider-independent wait prototype

**Durum:** Saf wait prototipi. CLI adapter'ı #614'te ayrıca eklendi.
Yuva CLI/panel, provider, servis, tmux ve canlı data root kullanılmadı.

## Karar

`yuva wait --from <worker-id> --after <message-id> [--timeout 30]` biçimindeki
açık, sonlu polling çağrısı #553'ün seçtiği ilk MVP yoluyla uyumludur. İşlevsel
taslak `prototypes/yuva-wait/wait.py` içindedir. Çağıran snapshot reader'ı,
doğrudan alıcının birebir saklanan hedeflerini ve iptal olayını sağlar; bu
prototip bunları çözmez veya kalıcılaştırmaz.

## Durum sözleşmesi

| Konu | Prototip kararı |
| --- | --- |
| Hedef | Yalnız çağıranın verdiği exact doğrudan `@recipient` değerleri; broadcast hedefi reddedilir. Fuzzy isim eşleşmesi yoktur. |
| Cursor | `after_id` tam ve snapshot'ta tekil bulunmalı. Eksik/çift cursor `cursor_unavailable`; tahmin yok. |
| Sıralama | Reader ekleme sıralı bir snapshot vermeli. Aynı snapshot'ta yinelenen message ID `source_invalid` üretir. |
| Bekleme | Monotonic deadline; timeout `0..300s`, poll interval `(0..2s]`. Tek çağrı en fazla bir mesaj döndürür. |
| İptal | `threading.Event`; bekleme aralığında hızlıca `cancelled` döner. Sinyali Event'e bağlamak dış CLI adapter'ının işidir. |
| Tekrar | Cursor bellekte tutulmaz. Aynı `after_id` ile tekrar çağrı aynı ID'yi yeniden verebilir; consumer `next_cursor`/message ID'yi kendisi kaydeder. Replay at-least-once gözlemdir, ack değildir. |
| Hata | Bozuk/gelecek şema ve belirsiz snapshot fail-closed; reader exception `source_error` olur. Bunlar yeniden gönderim veya mesaj yok kanıtı değildir. |
| Güven | Zarf iddiası yetki için kullanılmaz. Projection daima `source_trust=unverified`, `content_class=data_only`; metin komut/approval olarak yorumlanmaz. |

`read_snapshot` çağrısı bloklamayan veya kendi içinde bounded olmalıdır; timeout
ve cancellation, takılmış bir reader callback'ini kesemez. Üretim reader'ı
JSONL kuyruk bütünlüğü/bütçesi, tek bekleyen waiter politikası ve cursor
sahibini ayrıca tanımlamalıdır. Sohbet kaydı görev ataması, teslimi veya iş
tamamlanması anlamına gelmez; yürütülebilir iş kanonik atanmış görev olarak
kalır.

## Kapsam ve açık kapı

Bu dosyadaki prototip yalnız saf karar/bekleme kodudur; filesystem, persistence,
ack, provider write, task mutation, panel ve process lifecycle içermez. #614
ayrı CLI adapter'ı bounded JSONL reader ile bu saf işlevi çağırır. CLI
entegrasyonu kalıcı cursor/ack, tek waiter veya provider receipt eklemez; kabul
sınırları [`yuva-wait-cli-fixture-614.md`](yuva-wait-cli-fixture-614.md)
belgesindedir.

İlgili karar: [#553 chat komut teslimi MVP'si](chat-command-delivery-mvp-553.md).
Bu prototip onun provider-bağımsız polling seçimini daraltır; canlı teslim ya
da agent receipt'i iddiası eklemez.
