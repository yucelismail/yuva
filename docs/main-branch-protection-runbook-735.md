# Yuva #735 — `main` dalı koruması operatör runbooku

Bu yönerge GitHub repo ayarlarını operatörün uygulaması içindir. Bu görevde
GitHub hesabına veya repo ayarlarına erişilmedi; ruleset, branch protection,
push, merge ve workflow çalıştırması yapılmadı.

## Ön kontrol

1. GitHub’da doğru depoyu açın ve `Settings` → `General` içindeki **Default
   branch** değerini doğrulayın. Aşağıdaki adımlar yalnız bu değer gerçekten
   `main` ise uygulanır.
2. `main` dalında `.github/workflows/ci.yml` bulunduğunu doğrulayın.
3. Ruleset oluşturmadan önce `Actions` sekmesinde **CI** workflow’unun
   `main` push veya bir pull request çalıştırmasını tamamlayıp başarılı
   olduğunu görün. Workflow check’leri yalnız desteklenen olaylarda PR’a
   raporlanır; bu workflow `pull_request` ve `push` olaylarını kullanır.
4. Check seçim alanında workflow job adını kullanın: **`unittest`**. Workflow
   adı `CI` olsa da GitHub workflow job status check’ini job adıyla gösterir.
   Depoda başka bir workflow aynı job adını kullanıyorsa önce ad çakışmasını
   giderin; yinelenen job adları check’i belirsizleştirebilir.
   Syntax kontrolü ve Python 3.8/3.15 unittest adımları aynı `unittest`
   job’unda çalışır; branch protection’da bunların tamamını kapsayan tek check seçilir.
   Workflow’da matrix yoktur ve ek bir birleşik gate gerekmez.

## Branch ruleset oluşturma

1. Depo ana sayfasında **Settings**’i açın; sol menüde **Code and automation**
   altındaki **Rulesets** bölümüne gidin. **New ruleset** → **New branch
   ruleset** yolunu izleyin.
2. Ruleset’e örneğin `main-pr-ci` adını verin ve **Enforcement status** değerini
   **Active** seçin.
3. **Target branches** bölümünde yalnız `main` dalını hedefleyin.
4. **Branch protections** bölümünde **Require a pull request before merging**
   ve **Require status checks to pass before merging** seçeneklerini açın.
5. Required status check alanında **`unittest`** arayıp listeden seçin ve
   seçim alanına ekleyin. Varsa expected source olarak **GitHub Actions**’ı
   seçin. Onay sayısı veya güncel base branch şartı repo politikasına göre
   ayrıca belirlenebilir; bu runbook bu politikaları varsaymaz.
6. Bypass listesine kişi/ekip eklemeyin; istisna gerekiyorsa bunu ayrıca
   yetkilendirin. Kuralları ve hedef dalı gözden geçirdikten sonra **Create
   ruleset** ile kaydedin. Active ruleset kaydedildiği anda yürürlüğe girer.

GitHub’ın ruleset oluşturma adımları, durum kontrolü seçim alanı ve Active
durumunun etkisi [resmi ruleset yönergesinde](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository)
açıklanır. Workflow job check adı `<job name>` biçimindedir; bu depodaki
workflow’da ad `unittest` olarak sabitlenmiştir ([status check adları](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/troubleshooting-rules#troubleshooting-required-status-checks)).

## Ayarı doğrulama

- Rulesets sayfasında ruleset’in **Active** olduğunu, hedefinin `main`
  olduğunu ve iki koruma kuralının etkin olduğunu doğrulayın.
- Bir pull request açıp ya da mevcut bir PR’ı güncelleyip **Checks** bölümünde
  `unittest` job’unun son commit için tamamlandığını doğrulayın. Ruleset
  ayrıntıları PR’ın merge kutusunda da gerekli check’in geçtiğini göstermelidir.
- Check seçicide `unittest` görünmüyorsa workflow’un `main` veya PR üzerinde
  yakın zamanda başarılı çalıştığını kontrol edip sayfayı yenileyin. GitHub,
  required check’in depoda son yedi gün içinde başarılı tamamlanmış olmasını
  ister ([required check sorun giderme](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)).
- PR check’i beklemede kalırsa event’in `pull_request` veya `push` olduğunu ve
  workflow/job’un path filtresi ya da koşul nedeniyle atlanmadığını kontrol
  edin. Bu workflow’da path filtresi yoktur.
- Doğrulama için `main` dalına doğrudan push veya merge denemesi yapmayın.
  Ruleset görünümünü ve bir PR’ın merge koşullarını incelemek yeterlidir.

Repo ayarını düzenleyebilmek için repo admin erişimi veya `edit repository
rules` izni gerekir. Rulesets özelliği repo görünürlüğü ve planına göre
kullanılabilir; ayar ekranında seçenek yoksa repo yöneticisine başvurun.
