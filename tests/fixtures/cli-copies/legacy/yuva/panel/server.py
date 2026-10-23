#!/usr/bin/env python3
# 🪹 yuva web paneli — http://localhost:8686
#
# Tek dosya, stdlib HTTP sunucusu. Arayüz: panel/ui.html (her istekte diskten okunur).
# Veri: ~/yuva/{durum,gorevler}.json + mesaj.jsonl + ekran/<kimlik>.jsonl
# Sözleşme: /tmp/opencode/yuva-v2/SPEC.md
import fcntl
import json
import os
import random
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

KOK = Path(os.environ.get("YUVA_DIR") or (Path.home() / "yuva"))
DURUM = KOK / "durum.json"
GOREV = KOK / "gorevler.json"
BUS = KOK / "mesaj.jsonl"
EKRAN = KOK / "ekran"
KILIT_DOSYA = KOK / ".kilit"
ONLINE_SN = 30        # son kalp atışı bu süreden taze ise model çevrimiçi
MESAJ_SN = 200        # /api/veri'de dönen mesaj sayısı
EKRAN_SN = 60         # model başına dönen ekran satırı
KILIT = threading.RLock()   # süreç içi kritik bölge kilidi

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
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return varsayilan


def yaz(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def ekle(yol, satir):
    """jsonl dosyasına süreçler arası kilitli ekleme."""
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    with open(KILIT_DOSYA, "a+") as k:
        fcntl.flock(k, fcntl.LOCK_EX)
        try:
            with open(yol, "a", encoding="utf-8") as f:
                f.write(json.dumps(satir, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(k, fcntl.LOCK_UN)


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
    return (datetime.now().astimezone() - t).total_seconds() <= sn


def durum_oku():
    d = oku(DURUM, {"kullanicilar": {}, "rev": 0})
    d.setdefault("kullanicilar", {})
    d.setdefault("rev", 0)
    return d


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
    with KILIT:
        d = durum_oku()
        v = d["kullanicilar"].get(kimlik)
        yeni = v is None
        if yeni:
            v = {"katilma": simdi()}
            d["kullanicilar"][kimlik] = v
        v["arac"] = arac
        v["rol"] = rol
        v.setdefault("ad", None)
        if not v.get("ad"):
            v["ad"] = benzersiz_ad(d, g.get("ad") or kimlik, haric=kimlik)
        v["bagli"] = True
        v["son_gorulme"] = simdi()
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
    with KILIT:
        d = durum_oku()
        k = coz(d, kimlik)
        if not k:
            return 400, {"ok": False, "hata": f"bilinmeyen kimlik: {kimlik}"}
        v = d["kullanicilar"][k]
        dokun(d, k)
        durum_yaz(d)
        return 200, {"ok": True, "kimlik": k, "ad": adi(k, v), "rol": v.get("rol"),
                     "online": True}


def api_ayril(g):
    kimlik = str(g.get("kimlik") or "").strip()
    with KILIT:
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
    with KILIT:
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
    with KILIT:
        d = durum_oku()
        k = coz(d, kimlik)
        if not k:
            return 400, {"ok": False, "hata": f"bilinmeyen kimlik: {kimlik}"}
        v = d["kullanicilar"][k]
        v["rol"] = rol
        v["bas_denetci"] = bool(g.get("bas_denetci")) and rol == "denetci"
        durum_yaz(d)
        ek = " 🔍 BAŞ DENETÇİ" if v["bas_denetci"] else ""
        mesaj_ekle(k, f"🎖️ {adi(k, v)} artık {ROL_AD[rol]}{ek}", tur="durum", ad=adi(k, v))
    return 200, {"ok": True, "kimlik": k, "ad": adi(k, v), "rol": rol,
                 "bas_denetci": v["bas_denetci"]}


def api_yaz(g):
    metin = str(g.get("metin") or "").strip()
    if not metin:
        return 400, {"ok": False, "hata": "metin boş olamaz"}
    tur = g.get("tur") if g.get("tur") in TURLER else "not"
    with KILIT:
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
    with KILIT:
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
    with KILIT:
        d = durum_oku()
        k = coz(d, kimlik)
        if not k:
            return 400, {"ok": False, "hata": f"bilinmeyen kimlik: {kimlik}"}
        d["kullanicilar"][k]["not_"] = str(g.get("not_") or "")
        durum_yaz(d)
    return 200, {"ok": True, "kimlik": k}


def gorev_calistir(g):
    """Legacy panel task writes are retired; this copy cannot mutate the ledger."""
    return 410, {"ok": False, "hata": "legacy_task_writes_disabled"}


UCLAR = {
    "/api/katil": api_katil,
    "/api/kalp": api_kalp,
    "/api/ayril": api_ayril,
    "/api/ad": api_ad,
    "/api/rol": api_rol,
    "/api/yaz": api_yaz,
    "/api/ekran": api_ekran,
    "/api/not": api_not,
    "/api/gorev": gorev_calistir,
}


# ── anlık görüntü ────────────────────────────────────────────────────

def veri():
    with KILIT:
        d = durum_oku()
        g = oku(GOREV, {"siradaki": 1, "gorevler": []})
        ks = {}
        for k, v in d["kullanicilar"].items():
            ks[k] = {
                "kimlik": k,
                "ad": adi(k, v),
                "arac": v.get("arac", "diger"),
                "rol": v.get("rol", "isci"),
                "bas_denetci": bool(v.get("bas_denetci")),
                "katilma": v.get("katilma"),
                "son_gorulme": v.get("son_gorulme"),
                "son_okuma": v.get("son_okuma"),
                "bagli": bool(v.get("bagli")),
                "online": bool(v.get("bagli")) and taze(v.get("son_gorulme")),
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
        return (KOK / "panel" / "ui.html").read_text(encoding="utf-8")
    except Exception:
        return HTML_YEDEK


# ── HTTP ─────────────────────────────────────────────────────────────

class H(BaseHTTPRequestHandler):
    server_version = "yuva/2.0"
    protocol_version = "HTTP/1.1"

    def _gonder(self, kod, govde, tur="application/json; charset=utf-8"):
        if isinstance(govde, (dict, list)):
            govde = json.dumps(govde, ensure_ascii=False)
        b = govde.encode("utf-8") if isinstance(govde, str) else govde
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        try:
            self.wfile.write(b)
        except Exception:
            pass

    def do_GET(self):
        yol = (self.path.split("?")[0] or "/").rstrip("/") or "/"
        if yol in ("/api/veri", "/veri"):
            return self._gonder(200, veri())
        if yol in ("/", "/index.html"):
            return self._gonder(200, sayfa(), "text/html; charset=utf-8")
        return self._gonder(404, {"ok": False, "hata": "yol yok: " + yol})

    def do_POST(self):
        yol = (self.path.split("?")[0] or "/").rstrip("/")
        if yol == "/api/gorev":
            # Reject before reading/parsing request content or dispatching the
            # old unlocked task bridge. Use the supported canonical panel.
            return self._gonder(410, {
                "ok": False, "hata": "legacy_task_writes_disabled"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            ham = self.rfile.read(n) if n > 0 else b""
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
    print(f"🪹 panel: http://localhost:{a.port}  (veri: {KOK})")
    Sunucu((a.host, a.port), H).serve_forever()
