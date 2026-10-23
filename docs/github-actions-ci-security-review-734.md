# Yuva #734 — GitHub Actions CI güvenlik denetimi

**Tarih:** 2026-10-23
**Kapsam:** Salt-okunur inceleme: `.github/workflows/ci.yml` ve resmi action
release/permission belgeleri. Workflow veya GitHub repo ayarı değiştirilmedi;
test/runtime çalıştırılmadı.

## Sonuç

Statik incelemede PR kodunu ayrıcalıklı bir event altında çalıştıran bulgu
yok. Workflow `pull_request` kullanıyor; `pull_request_target`, `workflow_run`
veya PR verisini shell komutuna aktaran dinamik expression yok
(`ci.yml:3-7, 18-27`). Test komutu PR checkout'ından kod çalıştırıyor; bu
beklenen CI davranışı ve job token'ı en az yetkiyle sınırlandırılmış.

## Kontrol matrisi

| Kontrol | Gözlem | Değerlendirme |
|---|---|---|
| Event/context (`ci.yml:3-7`) | Tüm pull request'lerde ve `main` push'larında çalışır. `pull_request_target`/`workflow_run` yok; event alanı shell'e interpolate edilmiyor. | Fork PR kodu güvenilmeyen kod bağlamında kalıyor. |
| Token permission (`ci.yml:9-10`) | Workflow seviyesinde yalnız `contents: read`; diğer `GITHUB_TOKEN` permission kapsamları belirtilmiyor. | En az yetki. Checkout/test için yeterli; repo içeriği yazma, PR açma, deploy veya OIDC yetkisi istenmiyor. |
| Secrets/deploy (`ci.yml:18-27`) | `secrets.*`, environment, deploy action/komutu, artifact/cache upload veya self-hosted runner yok. | İncelenen workflow'da secret/deploy yüzeyi görülmedi. |
| Checkout (`ci.yml:18-19`) | Checkout action sabit commit SHA ile pinli. `persist-credentials` ayarı verilmedi; action varsayılanı `true`. | Düşük öncelikli sertleştirme önerisi: `with: persist-credentials: false` ekle. Sonraki adım authenticated Git kullanmıyor; çalışma alanında token'ı tutmaya ihtiyaç görünmüyor. |
| Action pinleri (`ci.yml:19, 22`) | Checkout SHA `3d3c42e5…273ba90b1`, resmi `v7.0.1` release commit'i; setup-python SHA `6d4fd22b…7c9ca0e0`, resmi `v7.1.0` release commit'iyle eşleşiyor. İki release de GitHub tarafından verified imzalı. | Tag yerine full commit SHA pinlenmiş; doğrulandı. |
| Runner/komut (`ci.yml:15-16, 24-27`) | `ubuntu-latest`, 30 dakika timeout ve sabit unittest komutu kullanılıyor. | Ayrıcalıklı/self-hosted host yok. `ubuntu-latest` güncellenen bir image alias'ıdır; tekrarlanabilirlik sürüm sabitlemesi kadar güçlü değildir. |

## Önerilen küçük sertleştirme

Checkout adımına şu ayarı eklemek token'ın test boyunca git credential olarak
kullanılmasını önler:

```yaml
      - name: Check out repository
        uses: actions/checkout@<aynı sabit SHA>
        with:
          persist-credentials: false
```

`actions/checkout` belgesi bu input'un varsayılanını `true` olarak tanımlar;
`false` authenticated Git komutlarının bu job'da çalışmayacağı durumda uygun
opt-out'tur. Bu, mevcut `contents: read` sınırının yanında ek bir azaltmadır;
incelemede sömürülebilir bir token-yazma yetkisi bulgusu tespit edilmedi.

GitHub fork PR'larını `pull_request` event'inde read-only token ve repo
secret'ları olmadan çalıştırır; `pull_request_target` ise daha yüksek güven
bağlamıdır. Bu workflow güvenli event'i seçiyor. Repo/organization Actions
ayarları incelenmedi; özel repo fork politikaları ve default permissions ayrıca
operatör tarafından doğrulanabilir.

Kaynaklar: [checkout v7.0.1 release](https://github.com/actions/checkout/releases/tag/v7.0.1),
[setup-python v7.1.0 release](https://github.com/actions/setup-python/releases/tag/v7.1.0),
[checkout `persist-credentials` input'u](https://github.com/actions/checkout#usage),
[fork PR event/token davranışı](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflows-in-forked-repositories),
[workflow permissions semantiği](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions),
[`pull_request_target` güven sınırı](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target).
