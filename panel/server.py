#!/usr/bin/env python3
# 🪹 yuva web paneli — http://localhost:8686
#
# Tek dosya, stdlib HTTP sunucusu. Arayüz: panel/ui.html (her istekte diskten okunur).
# Veri: ~/yuva/{durum,gorevler}.json + mesaj.jsonl + ekran/<kimlik>.jsonl
# Sözleşme: HTTP JSON API — uçlar UCLAR sözlüğünde tanımlıdır; istemci/kurallar
# için README.md ve protokol.md (yerel mutlak yol içermez).
#
# Kalıcılık kuralları (bu aşamada sağlamlaştırıldı):
#   * durum.json/gorevler.json okuma-değiştirme-yazma bölgeleri CLI ile ORTAK
#     KOK/.kilit dosyası üzerinde flock ile korunur (süreç içi RLock ile birlikte).
#   * Eksik/boş dosya varsayılanla başlar; var olan bozuk dosya sessizce
#     varsayılana çevrilmez, 500 + açık hata döner ve dosya yerinde bırakılır.
#   * Yazma benzersiz geçici dosya + os.replace ile atomiktir; kilit CLI
#     subprocess çalışırken asla açık tutulmaz (deadlock önlemi).
#   * POST doğrulaması fail-closed: gövde JSON çözümünden önce Content-Length
#     denetlenir (geçersiz/eksik gövde 400, 1 MiB üstü 413); /api/gorev denetle
#     için 'revize' alanı zorunlu JSON boolean (yoksa 400, sessiz onay yok).
#   * Kaynak denetimi: Host yalnız loopback adı + zorunlu gerçek port (403),
#     Origin varsa yalnız http scheme + doğrulanmış Host authority ile birebir
#     eşleşme ('null'/yabancı → 403), POST'ta Content-Type application/json
#     (aksi 415), OPTIONS'a CORS izni yok (405). Loopback dışı bind fail-closed
#     reddedilir; istemci adresi de loopback olmalı.
#     BU KİMLİK DOĞRULAMASI DEĞİLDİR: aynı UID altındaki süreçler yine `--from`
#     taklidi yapabilir ve durum/görev/mesaj dosyalarını doğrudan yazabilir.
import fcntl
import ipaddress
import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

CODE_ROOT = Path(__file__).resolve().parent.parent
KOK = Path(os.environ.get("YUVA_DIR") or (Path.home() / "yuva"))
DURUM = KOK / "durum.json"
GOREV = KOK / "gorevler.json"
BUS = KOK / "mesaj.jsonl"
EKRAN = KOK / "ekran"
KILIT_DOSYA = KOK / ".kilit"
CLI = CODE_ROOT / "bin" / "yuva"

ONLINE_SN = 30        # son kalp atışı bu süreden taze ise model çevrimiçi
MESAJ_SN = 200        # /api/veri'de dönen mesaj sayısı
EKRAN_SN = 60         # model başına dönen ekran satırı
GOVDE_SINIR = 1024 * 1024   # POST gövdesi üst sınırı (bayt); aşan istek gövdesi okunmadan 413
# Kaynak denetimi (Host/Origin) için kabul edilen loopback adları (köşeli parantezsiz).
# Bu liste bir güvenlik sınırı DEĞİL, yalnız tarayıcı kökenli CSRF/DNS-rebinding
# yazma vektörünü daraltan bir filtredir (ayrıntı: H._kaynak_denetimi).
LOOPBACK_ADLAR = ("localhost", "127.0.0.1", "::1")


def loopback_mi(deger):
    """--host / istemci adresi yalnız loopback ise True (127.0.0.0/8, ::1, localhost)."""
    h = (deger or "").strip().strip("[]").lower()
    if h in ("localhost", "::1"):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False
KILIT = threading.RLock()   # süreç içi kritik bölge kilidi


class DurumHatasi(RuntimeError):
    """Kalıcı JSON durum dosyası okunamadı/bozuk; sessiz varsayılana düşülmez."""


# Süreçler arası kilit: CLI (bin/yuva -> ekle_jsonl) ile AYNI dosya (KOK/.kilit).
# Kural: kilit yalnız JSON durum okuma-değiştirme-yazma bölgesinde tutulur; CLI
# subprocess çalıştırılırken (gorev_calistir) ASLA açık bırakılmaz, aksi halde
# çocuk süreç ekle_jsonl'de aynı kilidi beklerken karşılıklı bekleme (deadlock) olur.
KILIT_SN = 10.0               # kilit için azami bekleme (sn); süre aşımı = açık hata
_kilit_yerel = threading.local()


class dosya_kilidi:
    """KOK/.kilit üzerinde flock(LOCK_EX); aynı iş parçacığında iç içe geçebilir.

    flock() açık dosya tanımlayıcısına bağlıdır: farklı iş parçacıkları farklı
    tanımlayıcıyla açtığı için birbirini bekler (istenen davranış). İç içe çağrı
    aynı iş parçacığında yeniden kilitleme denemesi yapmaz; sayaçla izlenir ki
    JSONL ekleme (ekle) gibi alt çağrılar kendi kendini kilitlemesin.
    """

    def __init__(self, sn=KILIT_SN):
        self.sn = sn
        self._f = None

    def __enter__(self):
        derinlik = getattr(_kilit_yerel, "derinlik", 0)
        if derinlik == 0:
            KILIT_DOSYA.parent.mkdir(parents=True, exist_ok=True)
            try:
                f = open(KILIT_DOSYA, "a+", encoding="utf-8")
            except OSError as e:
                raise DurumHatasi(f"durum kilidi açılamadı ({KILIT_DOSYA}): {e}") from e
            bitis = time.monotonic() + self.sn
            while True:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= bitis:
                        f.close()
                        raise DurumHatasi(
                            f"durum kilidi alınamadı ({KILIT_DOSYA}, {self.sn:g} sn bekledi)")
                    time.sleep(0.05)
            self._f = f
        _kilit_yerel.derinlik = derinlik + 1
        return self

    def __exit__(self, *exc):
        _kilit_yerel.derinlik = max(0, getattr(_kilit_yerel, "derinlik", 1) - 1)
        if self._f is not None:
            try:
                fcntl.flock(self._f, fcntl.LOCK_UN)
            finally:
                self._f.close()
        return False


_YOK = object()          # oku(): "dosya yok/boş" ile geçerli JSON `null` ayrımı için


ROLLER = ("goreci", "isci", "denetci")
ROL_AD = {"goreci": "görevli", "isci": "işçi", "denetci": "denetçi"}
ARACLAR = ("claude", "codex", "opencode", "diger")
TURLER = ("not", "soru", "cevap", "rapor", "denetim", "gorev", "durum")
EKRAN_TURLERI = ("ekran", "komut", "sonuc", "baslik")


# ── yardımcılar ───────────────────────────────────────────────────────

def simdi():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def uid():
    return f"{int(time.time() * 1000):x}-{random.randint(1000, 9999)}"


def oku(p, varsayilan):
    """JSON okur. Dosya yoksa/sıfır baytsa varsayılan; bozuksa DurumHatasi.

    Var olan bozuk dosya sessizce varsayılana çevrilmez ve üzerine yazılmaz:
    hata çağırana taşınır (HTTP 500), dosya yerinde bırakılır ki elle onarılabilsin.
    """
    p = Path(p)
    try:
        ham = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return varsayilan
    except UnicodeDecodeError as e:
        raise DurumHatasi(f"{p.name} okunamadı (kodlama hatası): {e}") from e
    except OSError as e:
        raise DurumHatasi(f"{p.name} okunamadı: {e}") from e
    if not ham.strip():
        return varsayilan          # sıfır/boş dosya: yeni sayılır (kayıp veri yok)
    try:
        return json.loads(ham)
    except json.JSONDecodeError as e:
        raise DurumHatasi(
            f"{p.name} bozuk JSON (satır {e.lineno}, sütun {e.colno}: {e.msg}); "
            f"dosya değiştirilmedi, elle onarılmalı") from e


def yaz(p, v):
    """Dayanıklı atomik yazma: geçici dosya + os.replace + üst dizin fsync.

    Sabit adlı `.tmp` kullanılmaz (eşzamanlı yazımlarda birbirini ezerdi).
    Geçici dosya hedefin izin maskesini devralır; hata halinde artık bırakılmaz.
    """
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        mod = p.stat().st_mode & 0o777
    except OSError:
        mod = 0o644
    gecici = None
    yerine_koyuldu = False
    try:
        fd, ad = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
        gecici = Path(ad)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(v, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fchmod(f.fileno(), mod)
            os.fsync(f.fileno())
        os.replace(gecici, p)
        gecici = None
        yerine_koyuldu = True
        dizin_fd = os.open(p.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dizin_fd)
        finally:
            os.close(dizin_fd)
    except OSError as e:
        if yerine_koyuldu:
            raise DurumHatasi(
                f"{p.name} değiştirildi ancak üst dizin dayanıklılığı doğrulanamadı: {e}") from e
        raise DurumHatasi(f"{p.name} yazılamadı: {e}") from e
    finally:
        if gecici is not None:
            try:
                gecici.unlink(missing_ok=True)
            except OSError:
                pass


def ekle(yol, satir):
    """jsonl dosyasına süreçler arası kilitli ekleme (CLI ile aynı .kilit dosyası)."""
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    kayit = json.dumps(satir, ensure_ascii=False) + "\n"
    with dosya_kilidi():
        with open(yol, "a", encoding="utf-8") as f:
            f.write(kayit)


def guvenli(s):
    """Dosya adı güvenliği: dizin kaçışı imkânsız."""
    t = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in str(s))[:64]
    return ("_" + t.lstrip(".")) if t.startswith(".") else (t or "yok")


def taze(iso, sn=ONLINE_SN):
    try:
        t = datetime.fromisoformat(str(iso))
    except Exception:
        return False
    if t.tzinfo is None:
        t = t.astimezone()
    yas = (datetime.now().astimezone() - t).total_seconds()
    return 0 <= yas <= sn


def durum_oku():
    """durum.json'u katı okur: eksik/boş dosya = boş durum, bozuk dosya = DurumHatasi."""
    d = oku(DURUM, _YOK)
    if d is _YOK:
        return {"kullanicilar": {}, "rev": 0}
    if not isinstance(d, dict):
        raise DurumHatasi(f"{DURUM.name} kökü JSON nesnesi değil")
    ks = d.setdefault("kullanicilar", {})
    if not isinstance(ks, dict):
        raise DurumHatasi(f"{DURUM.name}: 'kullanicilar' JSON nesnesi olmalı")
    d.setdefault("rev", 0)
    return d


def gorev_oku():
    """gorevler.json'u katı okur: eksik/boş dosya = boş defter, bozuk dosya = DurumHatasi."""
    g = oku(GOREV, _YOK)
    if g is _YOK:
        return {"siradaki": 1, "gorevler": []}
    if not isinstance(g, dict):
        raise DurumHatasi(f"{GOREV.name} kökü JSON nesnesi değil")
    gs = g.setdefault("gorevler", [])
    if not isinstance(gs, list):
        raise DurumHatasi(f"{GOREV.name}: 'gorevler' liste olmalı")
    s = g.setdefault("siradaki", 1)
    if isinstance(s, bool) or not isinstance(s, int):
        raise DurumHatasi(f"{GOREV.name}: 'siradaki' tamsayı olmalı")
    return g


def durum_yaz(d):
    d["rev"] = int(d.get("rev", 0)) + 1
    yaz(DURUM, d)
    return d["rev"]


def coz(d, anahtar):
    """Kimlik çözümleme: önce anahtar, sonra görünen ad."""
    ks = d["kullanicilar"]
    if not anahtar:
        return None
    anahtar = str(anahtar)
    if anahtar in ks:
        return anahtar
    a = anahtar.lstrip("@").strip().lower()
    for k, v in ks.items():
        if str(v.get("ad") or k).lower() == a:
            return k
    return None


def adi(k, v):
    return v.get("ad") or k


def benzersiz_ad(d, ad, haric=None):
    alinan = {str(v.get("ad") or k).lower(): k
              for k, v in d["kullanicilar"].items() if k != haric}
    temel = (str(ad or "").strip() or "misafir")[:24]
    if temel.lower() not in alinan:
        return temel
    i = 2
    while f"{temel}-{i}".lower() in alinan:
        i += 1
    return f"{temel}-{i}"


def sorumlu_dogrula(d, kimlik, sorumlu_kimlik, rol=None):
    """sorumlu_kimlik kenarını rol kurallarına göre doğrula; (hedef, hata)."""
    if sorumlu_kimlik in (None, ""):
        return None, None
    ks = d["kullanicilar"]
    rol = rol or ks.get(kimlik, {}).get("rol", "isci")
    hedef = coz(d, sorumlu_kimlik)
    if not hedef:
        return None, f"bilinmeyen sorumlu kimliği: {sorumlu_kimlik}"
    if hedef == kimlik:
        return None, "kimlik kendisini sorumlu gösteremez"
    hedef_v = ks[hedef]
    hedef_rol = hedef_v.get("rol", "isci")
    if rol in ("goreci", "isci") and hedef_rol == "denetci":
        return hedef, None
    if (rol == "denetci" and hedef_rol == "denetci"
            and hedef_v.get("bas_denetci")):
        return hedef, None
    return None, "görevli/işçi denetçiye; denetçi yalnız baş denetçiye bağlanabilir"


def kimlik_rol_gecis_dogrula(d, kimlik, yeni_rol, bas_denetci=False):
    """Rol değişikliği mevcut ekip/baş denetçi bağlarını sessizce bozamaz."""
    ks = d["kullanicilar"]
    v = ks.get(kimlik, {})
    eski_rol = v.get("rol", "isci")
    if bas_denetci and yeni_rol != "denetci":
        return "baş denetçi yalnız denetçi rolünde olabilir"
    if yeni_rol != "denetci" and v.get("bas_denetci"):
        return "baş denetçinin rolü değişmeden önce baş denetçilik kaldırılmalı"
    baglilar = [k for k, x in ks.items() if x.get("sorumlu_kimlik") == kimlik]
    if yeni_rol != "denetci" and baglilar:
        return "ekip üyeleri bağlı; önce sorumlu bağlarını kaldırın veya yeniden atayın"
    sorumlu = v.get("sorumlu_kimlik")
    if sorumlu:
        hedef, hata = sorumlu_dogrula(d, kimlik, sorumlu, rol=yeni_rol)
        if hata:
            return "mevcut sorumlu bağı yeni rolle geçersiz: " + hata
    if eski_rol != "denetci" and yeni_rol == "denetci" and sorumlu:
        return "denetçi yapılacak kimliğin önce sorumlu bağı kaldırılmalı"
    return None


def bas_denetci_ata(d, kimlik, etkin):
    """Tek etkin baş denetçiyi kilitli durum nesnesinde ata/kaldır."""
    ks = d["kullanicilar"]
    v = ks.get(kimlik)
    if not v:
        return "bilinmeyen kimlik"
    if v.get("rol", "isci") != "denetci":
        return "baş denetçi yalnız denetçi rolünden seçilebilir"
    if etkin:
        eskiler = [k for k, x in ks.items()
                   if k != kimlik and x.get("bas_denetci")]
        if eskiler:
            # Inspector raporları baş denetçi değişiminde yeni başa taşınır.
            for x in ks.values():
                if (x.get("rol") == "denetci"
                        and x.get("sorumlu_kimlik") in eskiler):
                    x["sorumlu_kimlik"] = kimlik
            for eski in eskiler:
                ks[eski]["bas_denetci"] = False
        v.pop("sorumlu_kimlik", None)
        v["bas_denetci"] = True
        return None
    if v.get("bas_denetci"):
        if any(k != kimlik and x.get("rol") == "denetci"
               and x.get("sorumlu_kimlik") == kimlik for k, x in ks.items()):
            return "baş denetçiye bağlı denetçiler var; önce onları yeniden atayın"
        v["bas_denetci"] = False
    return None


def mesaj_ekle(kimden, metin, kime="@hepsi", tur="not", ad=None, kanal="sohbet"):
    m = {"id": uid(), "ts": simdi(), "kimden": kimden, "kime": kime or "@hepsi",
         "tur": tur if tur in TURLER else "not", "metin": metin,
         "ad": ad or kimden, "kanal": kanal}
    ekle(BUS, m)
    return m


def mesajlar(n=MESAJ_SN):
    if not BUS.exists():
        return []
    try:
        satirlar = BUS.read_text(encoding="utf-8", errors="replace").splitlines()[-n * 3:]
    except Exception:
        return []
    ms = []
    for s in satirlar:
        try:
            ms.append(json.loads(s))
        except Exception:
            continue
    return ms[-n:]


def ekran_yaz(kimlik, ad, satir, tur="ekran"):
    kayit = {"ts": simdi(), "kimlik": kimlik, "ad": ad,
             "tur": tur if tur in EKRAN_TURLERI else "ekran", "satir": satir}
    ekle(EKRAN / (guvenli(kimlik) + ".jsonl"), kayit)
    return kayit


def tum_ekranlar():
    out = {}
    if not EKRAN.exists():
        return out
    for f in sorted(EKRAN.glob("*.jsonl")):
        satirlar = []
        try:
            for s in f.read_text(encoding="utf-8", errors="replace").splitlines()[-EKRAN_SN:]:
                try:
                    satirlar.append(json.loads(s))
                except Exception:
                    continue
        except Exception:
            continue
        if satirlar:
            out[f.stem] = satirlar
    return out


def dokun(d, k):
    """Kalp atışı: son görülmeyi tazele (kimlik anahtarı hazır olmalı)."""
    v = d["kullanicilar"][k]
    v["son_gorulme"] = simdi()


# ── API uçları ────────────────────────────────────────────────────────

def api_katil(g):
    kimlik = str(g.get("kimlik") or "").strip()
    if not kimlik:
        return 400, {"ok": False, "hata": "kimlik gerekli"}
    arac = g.get("arac") if g.get("arac") in ARACLAR else "diger"
    rol = g.get("rol") if g.get("rol") in ROLLER else "isci"
    with KILIT, dosya_kilidi():
        d = durum_oku()
        v = d["kullanicilar"].get(kimlik)
        yeni = v is None
        if not yeni:
            hata = kimlik_rol_gecis_dogrula(d, kimlik, rol)
            if hata:
                return 409, {"ok": False, "hata": hata}
        if yeni:
            v = {"katilma": simdi()}
            d["kullanicilar"][kimlik] = v
        v["arac"] = arac
        v["rol"] = rol
        v.setdefault("ad", None)
        if not v.get("ad"):
            v["ad"] = benzersiz_ad(d, g.get("ad") or kimlik, haric=kimlik)
        zaten_bagli = bool(v.get("bagli"))
        v["bagli"] = True
        v["son_gorulme"] = simdi()
        # Ayrılmış kimlik eski heartbeat zamanıyla çevrimiçi dönmesin.
        if not zaten_bagli:
            v.pop("son_kalp", None)
        ad = adi(kimlik, v)
        if not v.get("duyuruldu"):
            v["duyuruldu"] = True
            mesaj_ekle(kimlik, f"🟢 {ad} bağlandı (arac: {arac}, rol: {ROL_AD[rol]})",
                       tur="durum", ad=ad)
        durum_yaz(d)
    return 200, {"ok": True, "kimlik": kimlik, "ad": ad, "rol": rol,
                 "bas_denetci": bool(v.get("bas_denetci"))}


def api_kalp(g):
    kimlik = str(g.get("kimlik") or "").strip()
    with KILIT, dosya_kilidi():
        d = durum_oku()
        k = coz(d, kimlik)
        if not k:
            return 400, {"ok": False, "hata": f"bilinmeyen kimlik: {kimlik}"}
        v = d["kullanicilar"][k]
        if not v.get("bagli"):
            return 409, {"ok": False, "hata": "kimlik bağlı değil"}
        v["son_kalp"] = simdi()
        durum_yaz(d)
        return 200, {"ok": True, "kimlik": k, "ad": adi(k, v), "rol": v.get("rol"),
                     "online": True}


def api_ayril(g):
    kimlik = str(g.get("kimlik") or "").strip()
    with KILIT, dosya_kilidi():
        d = durum_oku()
        k = coz(d, kimlik)
        if not k:
            return 400, {"ok": False, "hata": f"bilinmeyen kimlik: {kimlik}"}
        v = d["kullanicilar"][k]
        v["bagli"] = False
        v["duyuruldu"] = False
        durum_yaz(d)
        mesaj_ekle(k, f"⚫ {adi(k, v)} ayrıldı", tur="durum", ad=adi(k, v))
    return 200, {"ok": True, "kimlik": k}


def api_ad(g):
    kimlik = str(g.get("kimlik") or "").strip()
    yeni = str(g.get("ad") or "").strip()
    if not yeni:
        return 400, {"ok": False, "hata": "ad gerekli"}
    with KILIT, dosya_kilidi():
        d = durum_oku()
        k = coz(d, kimlik)
        if not k:
            return 400, {"ok": False, "hata": f"bilinmeyen kimlik: {kimlik}"}
        v = d["kullanicilar"][k]
        eski = adi(k, v)
        v["ad"] = benzersiz_ad(d, yeni, haric=k)
        durum_yaz(d)
        if v["ad"] != eski:
            mesaj_ekle(k, f"🏷️ {eski} → {v['ad']} adını aldı", tur="durum", ad=v["ad"])
    return 200, {"ok": True, "kimlik": k, "ad": v["ad"]}


def api_rol(g):
    kimlik = str(g.get("kimlik") or "").strip()
    rol = str(g.get("rol") or "").strip()
    if rol not in ROLLER:
        return 400, {"ok": False, "hata": f"geçersiz rol: {rol}"}
    with KILIT, dosya_kilidi():
        d = durum_oku()
        k = coz(d, kimlik)
        if not k:
            return 400, {"ok": False, "hata": f"bilinmeyen kimlik: {kimlik}"}
        v = d["kullanicilar"][k]
        bas_istegi = bool(g.get("bas_denetci")) and rol == "denetci"
        hata = kimlik_rol_gecis_dogrula(d, k, rol, bas_denetci=bas_istegi)
        if hata:
            return 409, {"ok": False, "hata": hata}
        v["rol"] = rol
        if bas_istegi:
            hata = bas_denetci_ata(d, k, True)
            if hata:
                return 409, {"ok": False, "hata": hata}
        elif v.get("bas_denetci"):
            hata = bas_denetci_ata(d, k, False)
            if hata:
                return 409, {"ok": False, "hata": hata}
        else:
            v["bas_denetci"] = False
        durum_yaz(d)
        ek = " 🔍 BAŞ DENETÇİ" if v["bas_denetci"] else ""
        mesaj_ekle(k, f"🎖️ {adi(k, v)} artık {ROL_AD[rol]}{ek}", tur="durum", ad=adi(k, v))
    return 200, {"ok": True, "kimlik": k, "ad": adi(k, v), "rol": rol,
                 "bas_denetci": v["bas_denetci"]}


def api_sorumlu(g):
    """Açık ekip bağı yazımı. API loopback kaynak denetimi yapar ama kimlik doğrulamaz."""
    kimlik = str(g.get("kimlik") or "").strip()
    if not kimlik or "sorumlu_kimlik" not in g:
        return 400, {"ok": False, "hata": "kimlik ve sorumlu_kimlik alanları gerekli"}
    with KILIT, dosya_kilidi():
        d = durum_oku()
        k = coz(d, kimlik)
        if not k:
            return 400, {"ok": False, "hata": f"bilinmeyen kimlik: {kimlik}"}
        v = d["kullanicilar"][k]
        ham = g.get("sorumlu_kimlik")
        if ham is None or ham == "":
            v.pop("sorumlu_kimlik", None)
        else:
            hedef, hata = sorumlu_dogrula(d, k, str(ham).strip())
            if hata:
                return 400, {"ok": False, "hata": hata}
            v["sorumlu_kimlik"] = hedef
        durum_yaz(d)
        sonuc = v.get("sorumlu_kimlik")
    return 200, {"ok": True, "kimlik": k, "sorumlu_kimlik": sonuc}


def api_bas_denetci(g):
    """Tek baş denetçiyi ata/kaldır; `etkin` JSON boolean olmalıdır.

    Uçta kullanıcı kimlik doğrulaması yoktur; loopback filtresi yetki kanıtı değildir.
    """
    kimlik = str(g.get("kimlik") or "").strip()
    etkin = g.get("etkin")
    if not kimlik or not isinstance(etkin, bool):
        return 400, {"ok": False, "hata": "kimlik ve boolean etkin alanları gerekli"}
    with KILIT, dosya_kilidi():
        d = durum_oku()
        k = coz(d, kimlik)
        if not k:
            return 400, {"ok": False, "hata": f"bilinmeyen kimlik: {kimlik}"}
        hata = bas_denetci_ata(d, k, etkin)
        if hata:
            return 409, {"ok": False, "hata": hata}
        durum_yaz(d)
        secili = next((x for x, v in d["kullanicilar"].items()
                       if v.get("bas_denetci")), None)
    return 200, {"ok": True, "bas_denetci": secili}


def api_yaz(g):
    metin = str(g.get("metin") or "").strip()
    if not metin:
        return 400, {"ok": False, "hata": "metin boş olamaz"}
    tur = g.get("tur") if g.get("tur") in TURLER else "not"
    with KILIT, dosya_kilidi():
        d = durum_oku()
        ham = str(g.get("kimden") or "kullanici").strip()
        if ham.lower() in ("", "kullanici", "kullanıcı", "sen", "user", "human"):
            kimden, ad = "kullanici", "Kullanıcı"
        else:
            k = coz(d, ham)
            if k:
                kimden, ad = k, adi(k, d["kullanicilar"][k])
                dokun(d, k)
                durum_yaz(d)
            else:
                kimden = ad = ham.lstrip("@") or "kullanici"
        kime = str(g.get("kime") or "@hepsi").strip()
        if kime and not kime.startswith("#"):
            hedef = kime.lstrip("@")
            kk = coz(d, hedef)
            kime = "@" + (adi(kk, d["kullanicilar"][kk]) if kk else hedef)
        m = mesaj_ekle(kimden, metin, kime=kime, tur=tur, ad=ad)
    return 200, {"ok": True, "mesaj": m}


def api_ekran(g):
    kimlik = str(g.get("kimlik") or "").strip()
    satir = str(g.get("satir") or "").rstrip()
    if not kimlik:
        return 400, {"ok": False, "hata": "kimlik gerekli"}
    if not satir:
        return 400, {"ok": False, "hata": "satir boş olamaz"}
    tur = g.get("tur") if g.get("tur") in EKRAN_TURLERI else "ekran"
    with KILIT, dosya_kilidi():
        d = durum_oku()
        k = coz(d, kimlik)
        ad = adi(k, d["kullanicilar"][k]) if k else kimlik
        kayit = ekran_yaz(k or kimlik, ad, satir, tur)
        if k:
            dokun(d, k)
            durum_yaz(d)
    return 200, {"ok": True, "ts": kayit["ts"], "kimlik": k or kimlik, "ad": ad}


def api_not(g):
    kimlik = str(g.get("kimlik") or "").strip()
    with KILIT, dosya_kilidi():
        d = durum_oku()
        k = coz(d, kimlik)
        if not k:
            return 400, {"ok": False, "hata": f"bilinmeyen kimlik: {kimlik}"}
        d["kullanicilar"][k]["not_"] = str(g.get("not_") or "")
        durum_yaz(d)
    return 200, {"ok": True, "kimlik": k}


def ust_gorev_id_coz(deger):
    """API parent ID'sini kanonik pozitif int'e dönüştür; whitespace'i reddet."""
    if isinstance(deger, bool):
        raise ValueError("boolean görev ID olamaz")
    if isinstance(deger, int):
        if deger < 1:
            raise ValueError("görev ID pozitif olmalı")
        return deger
    if (not isinstance(deger, str) or not deger
            or deger[0] not in "123456789"
            or any(karakter not in "0123456789" for karakter in deger[1:])):
        raise ValueError("kanonik pozitif tamsayı gerekli")
    return int(deger)


def gorev_calistir(g):
    """Görev mantığı tek yerde (bin/yuva) yaşar; burada yalnız köprü var.

    DİKKAT: subprocess çalışırken süreçler arası kilit (dosya_kilidi) AÇILMAZ —
    CLI de aynı KOK/.kilit dosyasını ekle_jsonl içinde kullanır; kilit açık
    tutulursa çocuk süreç bekler, biz de onu bekleriz (deadlock). Bu yüzden görev
    köprüsü kilitsiz çalışır; dosya tutarlılığı CLI'nin kendi yazma sırasına aittir.
    """
    islem = str(g.get("islem") or "").strip()
    if islem not in ("ekle", "ata", "al", "teslim", "ilk-kontrol", "denetle", "iptal"):
        return 400, {"ok": False, "hata": f"geçersiz işlem: {islem}"}
    if islem != "ekle" and "ust_gorev_id" in g:
        return 400, {"ok": False,
                     "hata": "ust_gorev_id yalnız ekle işleminde kullanılabilir"}
    # Fail-closed denetim kararı: 'revize' alanı ZORUNLU ve JSON boolean olmalı.
    # Eksik/yanlış tipte sessizce "--onayla"ya düşmek (fail-open) kaldırıldı.
    if islem == "denetle" and not isinstance(g.get("revize"), bool):
        return 400, {"ok": False,
                     "hata": "denetle için 'revize' alanı JSON boolean olmalı "
                             "(true=revize iste, false=onayla)"}
    if islem == "ilk-kontrol" and not isinstance(g.get("revize"), bool):
        return 400, {"ok": False,
                     "hata": "ilk-kontrol için 'revize' alanı JSON boolean olmalı "
                             "(true=revize iste, false=onayla)"}
    if not CLI.exists():
        return 500, {"ok": False, "hata": f"CLI bulunamadı: {CLI}"}
    args = [sys.executable, str(CLI), "gorev", islem]
    if islem == "ekle":
        if not g.get("baslik"):
            return 400, {"ok": False, "hata": "baslik gerekli"}
        if not g.get("gorevli"):
            return 400, {"ok": False, "hata": "yeni görev için gorevli gerekli"}
        ust_gorev_id = None
        if "ust_gorev_id" in g and g["ust_gorev_id"] is not None:
            try:
                ust_gorev_id = ust_gorev_id_coz(g["ust_gorev_id"])
            except ValueError:
                return 400, {"ok": False,
                             "hata": "ust_gorev_id boşluksuz kanonik pozitif tamsayı olmalı; kök görev için null kullanın"}
        args.append(str(g["baslik"]))
        if g.get("detay"):
            args += ["--detay", str(g["detay"])]
        if g.get("ata"):
            args += ["--ata", str(g["ata"])]
        args += ["--gorevli", str(g["gorevli"])]
        if ust_gorev_id is not None:
            args += ["--ust-gorev", str(ust_gorev_id)]
    else:
        if not g.get("id"):
            return 400, {"ok": False, "hata": "id gerekli"}
        args.append(str(g["id"]))
        if islem == "ata" and g.get("kime"):
            args.append(str(g["kime"]))
        if islem == "ata" and g.get("gorevli"):
            args += ["--gorevli", str(g["gorevli"])]
    args += ["--from", str(g.get("kimden") or "kullanici")]
    if g.get("not_"):
        args += ["--not", str(g["not_"])]
    if islem in ("denetle", "ilk-kontrol"):
        # buraya yalnız doğrulanmış boolean ile gelinir (yukarıdaki 400 kapısı)
        args.append("--revize" if g["revize"] else "--onayla")
    env = dict(os.environ)
    env["YUVA_DIR"] = str(KOK)
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=15, env=env)
    except Exception as e:
        return 500, {"ok": False, "hata": f"çalıştırma hatası: {e}"}
    cikti = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0:
        return 400, {"ok": False, "hata": cikti or "CLI hata verdi", "cikti": cikti}
    return 200, {"ok": True, "islem": islem, "cikti": cikti}


UCLAR = {
    "/api/katil": api_katil,
    "/api/kalp": api_kalp,
    "/api/ayril": api_ayril,
    "/api/ad": api_ad,
    "/api/rol": api_rol,
    "/api/sorumlu": api_sorumlu,
    "/api/bas-denetci": api_bas_denetci,
    "/api/yaz": api_yaz,
    "/api/ekran": api_ekran,
    "/api/not": api_not,
    "/api/gorev": gorev_calistir,
}


# ── anlık görüntü ────────────────────────────────────────────────────

def veri():
    """Tek kilitli kritik bölgede tutarlı anlık görüntü (durum + görev aynı rev'den).

    Salt okunur; CLI subprocess çağrılmaz, bu yüzden kilit burada güvenle tutulur.
    """
    with KILIT, dosya_kilidi():
        d = durum_oku()
        g = gorev_oku()
        ks = {}
        for k, v in d["kullanicilar"].items():
            ks[k] = {
                "kimlik": k,
                "ad": adi(k, v),
                "arac": v.get("arac", "diger"),
                "rol": v.get("rol", "isci"),
                "bas_denetci": bool(v.get("bas_denetci")),
                "sorumlu_kimlik": v.get("sorumlu_kimlik"),
                "katilma": v.get("katilma"),
                "son_gorulme": v.get("son_gorulme"),
                "son_kalp": v.get("son_kalp"),
                "son_okuma": v.get("son_okuma"),
                "bagli": bool(v.get("bagli")),
                "online": bool(v.get("bagli")) and taze(v.get("son_kalp")),
                "not_": v.get("not_", ""),
            }
        return {"ok": True, "simdi": simdi(), "online_sn": ONLINE_SN,
                "rev": d.get("rev", 0), "kullanicilar": ks,
                "gorevler": g.get("gorevler", []), "mesajlar": mesajlar(),
                "ekranlar": tum_ekranlar()}


HTML_YEDEK = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<title>🪹 Yuva</title></head><body style="background:#0d1117;color:#e6edf3;
font:14px ui-monospace,monospace;padding:24px">
<h1>🪹 YUVA</h1>
<p>Arayüz dosyası okunamadı: <code>panel/ui.html</code></p>
<p>Panel API çalışıyor: <a style="color:#58a6ff" href="/api/veri">/api/veri</a></p>
</body></html>"""


def sayfa():
    try:
        return (CODE_ROOT / "panel" / "ui.html").read_text(encoding="utf-8")
    except Exception:
        return HTML_YEDEK


# ── HTTP ─────────────────────────────────────────────────────────────

class H(BaseHTTPRequestHandler):
    server_version = "yuva/2.0"
    protocol_version = "HTTP/1.1"

    # ── kaynak (Host/Origin/Content-Type) denetimi ───────────────────────
    # DİKKAT — BU BİR KİMLİK DOĞRULAMASI DEĞİLDİR. Amacı yalnız tarayıcı
    # kökenli CSRF/DNS-rebinding ile yazma vektörünü daraltmaktır. Aynı OS
    # kullanıcısı (UID) altındaki herhangi bir süreç yine `--from` taklidi
    # yapabilir (aktör istemci gövdesinden gelir) ve durum.json/gorevler.json/
    # mesaj.jsonl dosyalarını doğrudan yazabilir. Bu yüzden loopback dışı bind
    # fail-closed reddedilir (main) ve istemci adresi de loopback olmalıdır:
    # uzaktan erişim bu görevde desteklenmez.
    IZINLI_HOSTLAR = set(LOOPBACK_ADLAR)   # main() somut loopback --host değerini ekler
    SUNUCU_PORT = None                     # main() gerçek dinleme portu ile doldurur

    @staticmethod
    def _host_ayristir(ham):
        """Host başlığını (ad, port) olarak çözer; port yoksa ''.

        'localhost:8686' → ('localhost', '8686'); '[::1]:8686' → ('::1', '8686');
        'localhost' → ('localhost', ''). Ad köşeli parantezden arındırılıp
        küçük harfe çevrilir.
        """
        ham = (ham or "").strip()
        if ham.startswith("["):                       # köşeli parantezli IPv6
            kapanis = ham.find("]")
            if kapanis < 0:
                return ham.lower(), ""
            kalan = ham[kapanis + 1:]
            return ham[1:kapanis].lower(), (kalan[1:] if kalan.startswith(":") else "")
        if ham.count(":") == 1:
            ad, _, port = ham.partition(":")
            return ad.lower(), port
        return ham.lower(), ""                        # portsuz ya da belirsiz

    def _origin_gecerli(self, ham, host_ad, host_port):
        """Origin yalnız http://<doğrulanmış Host authority> ile birebir eşleşirse geçer.

        Kural: şema http olmalı (panel http ile sunulur; https kabul edilmez),
        ad loopback listesinde olmalı ve host+port doğrulanmış Host authority ile
        aynı olmalı. Böylece 'Host: localhost:8686' + 'Origin: http://başka:8686'
        gibi uyumsuz (ve rebinding şüpheli) birleşimler reddedilir.
        """
        try:
            p = urlsplit(ham)
        except ValueError:
            return False
        if p.scheme != "http" or not p.hostname:
            return False
        oh = p.hostname.lower()
        if oh not in self.IZINLI_HOSTLAR:
            return False
        try:
            beklenen_port = int(host_port)
        except (TypeError, ValueError):
            return False
        if (p.port or 80) != beklenen_port:
            return False
        return oh == host_ad

    def _kaynak_denetimi(self, post=False):
        """Host + Origin (+ POST'ta Content-Type) fail-closed denetimi.

        Dönüş: None (geçti) veya (http_kodu, govde). JSON çözümünden ve uç
        çağrısından ÖNCE çalışır. Origin yokluğu (CLI/urllib istemcisi)
        desteklenir; 'null' veya farklı origin reddedilir.
        """
        # Gerçek istemci de loopback olmalı (bind denetimine ek savunma katmanı).
        ip = self.client_address[0] if self.client_address else ""
        if ip and not loopback_mi(ip):
            return 403, {"ok": False, "hata": f"loopback dışı istemci: {ip}"}
        ham_host = self.headers.get("Host")
        if not ham_host or not str(ham_host).strip():
            return 403, {"ok": False, "hata": "Host başlığı gerekli"}
        ad, port = self._host_ayristir(ham_host)
        if ad not in self.IZINLI_HOSTLAR:
            return 403, {"ok": False,
                         "hata": f"izin verilmeyen Host: {str(ham_host).strip()!r} (yalnız loopback)"}
        if not port:
            # Standart dışı port kullanıldığı için portsuz Host kabul edilmez.
            return 403, {"ok": False,
                         "hata": f"Host başlığı port içermeli (beklenen {self.SUNUCU_PORT})"}
        if self.SUNUCU_PORT is not None and port != str(self.SUNUCU_PORT):
            return 403, {"ok": False,
                         "hata": f"izin verilmeyen Host portu: {port} (beklenen {self.SUNUCU_PORT})"}
        ham_origin = self.headers.get("Origin")
        if ham_origin is not None:
            o = str(ham_origin).strip()
            if not o or o.lower() == "null" or not self._origin_gecerli(o, ad, port):
                return 403, {"ok": False, "hata": f"izin verilmeyen Origin: {o!r}"}
        if post:
            ct = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ct != "application/json":
                return 415, {"ok": False,
                             "hata": "POST için Content-Type application/json olmalı "
                                     f"(gelen: {self.headers.get('Content-Type')!r})"}
        return None

    def _gonder(self, kod, govde, tur="application/json; charset=utf-8", kapat=False):
        if isinstance(govde, (dict, list)):
            govde = json.dumps(govde, ensure_ascii=False)
        b = govde.encode("utf-8") if isinstance(govde, str) else govde
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        if kapat:
            # okunmayan gövde baytları sonraki isteğin çerçevesini bozmasın
            self.close_connection = True
            self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(b)
        except Exception:
            pass

    def _durum_hatasi(self, e):
        """Kalıcı durum hatasını görünür kıl: stderr + açık JSON yanıtı (sessiz düşüş yok)."""
        print(f"⚠️ {e}", file=sys.stderr, flush=True)
        return self._gonder(500, {"ok": False, "hata": f"kalıcı durum hatası: {e}"})

    def _govde_oku(self):
        """POST gövdesini sınırlı ve fail-closed okur.

        Dönüş: (govde_baytlari, hata) — hata (kod, govde) demetidir.
        JSON çözümünden ve uç çağrısından ÖNCE çalışır. Gövde hiç okunmadığı
        durumlarda (413/geçersiz uzunluk) bağlantı kapatılır ki kalan baytlar
        sonraki isteğin çerçevesini bozmasın.
        """
        if self.headers.get("Transfer-Encoding"):
            return None, (400, {"ok": False,
                                "hata": "Transfer-Encoding desteklenmiyor; Content-Length kullanın"})
        ham_cl = self.headers.get("Content-Length")
        if ham_cl is None:
            return b"", None          # gövdesiz istek: mevcut istemci sözleşmesi korunur
        cl = str(ham_cl).strip()
        if not cl.isdigit():
            return None, (400, {"ok": False, "hata": f"geçersiz Content-Length: {ham_cl!r}"})
        n = int(cl)
        if n > GOVDE_SINIR:
            return None, (413, {"ok": False,
                                "hata": f"gövde çok büyük: {n} bayt > {GOVDE_SINIR} bayt sınır"})
        if n == 0:
            return b"", None
        try:
            ham = self.rfile.read(n)
        except Exception as e:
            return None, (400, {"ok": False, "hata": f"gövde okunamadı: {e}"})
        if len(ham) != n:
            return None, (400, {"ok": False,
                                "hata": f"eksik gövde: {len(ham)}/{n} bayt alındı"})
        return ham, None

    def do_GET(self):
        yol = (self.path.split("?")[0] or "/").rstrip("/") or "/"
        hata = self._kaynak_denetimi()
        if hata:
            return self._gonder(hata[0], hata[1])
        if yol in ("/api/veri", "/veri"):
            try:
                return self._gonder(200, veri())
            except DurumHatasi as e:
                return self._durum_hatasi(e)
        if yol in ("/", "/index.html"):
            return self._gonder(200, sayfa(), "text/html; charset=utf-8")
        return self._gonder(404, {"ok": False, "hata": "yol yok: " + yol})

    def do_OPTIONS(self):
        """CORS ön-uçuşuna izin verilmez: Access-Control-Allow-* üretilmez."""
        self.close_connection = True
        self.send_response(405)
        self.send_header("Allow", "GET, POST")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_POST(self):
        yol = (self.path.split("?")[0] or "/").rstrip("/")
        hata = self._kaynak_denetimi(post=True)
        if hata:
            # Gövde okunmadı: kalan baytlar sonraki isteğin çerçevesini bozmasın.
            return self._gonder(hata[0], hata[1], kapat=True)
        ham, hata = self._govde_oku()
        if hata:
            kod, govde = hata
            return self._gonder(kod, govde, kapat=True)
        try:
            g = json.loads(ham.decode("utf-8")) if ham else {}
            if not isinstance(g, dict):
                raise ValueError("gövde JSON nesnesi olmalı")
        except Exception as e:
            return self._gonder(400, {"ok": False, "hata": f"geçersiz JSON: {e}"})
        fn = UCLAR.get(yol)
        if not fn:
            return self._gonder(404, {"ok": False, "hata": "uç yok: " + yol})
        try:
            kod, cevap = fn(g)
        except DurumHatasi as e:
            return self._durum_hatasi(e)
        except Exception as e:
            return self._gonder(500, {"ok": False, "hata": f"sunucu hatası: {e}"})
        return self._gonder(kod, cevap)

    def log_message(self, *a):
        pass


class Sunucu(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="🪹 yuva paneli")
    ap.add_argument("--port", type=int, default=8686)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    KOK.mkdir(parents=True, exist_ok=True)
    EKRAN.mkdir(parents=True, exist_ok=True)
    # Kaynak denetimi gerçek dinleme portuna bağlanır. Loopback dışı bind
    # fail-closed REDDEDİLİR: kimlik doğrulama yokken uzaktaki bir istemci
    # 'Host: localhost' taklidi yapabilir; bu görevde uzaktan erişim
    # desteklenmez (istek: uzaktan erişim yok). Gerçek güven sınırı için ayrı
    # OS kullanıcısı + unix soket (SO_PEERCRED) gerekir.
    if not loopback_mi(a.host):
        sys.exit(f"❌ --host {a.host!r} loopback dışı: bu sunucuda kimlik doğrulama YOK, "
                 "uzaktan erişim desteklenmez (yalnız localhost/127.0.0.1/::1).")
    H.SUNUCU_PORT = a.port
    H.IZINLI_HOSTLAR.add((a.host or "").strip().strip("[]").lower())
    print(f"🪹 panel: http://localhost:{a.port}  (veri: {KOK})")
    Sunucu((a.host, a.port), H).serve_forever()
