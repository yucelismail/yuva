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
#   * Yazma benzersiz geçici dosya + os.replace ile atomiktir. Görev köprüsü
#     v2 CLI görev mantığını principal ile aynı süreçte çağırır.
#   * POST doğrulaması fail-closed: gövde JSON çözümünden önce Content-Length
#     denetlenir (geçersiz/eksik gövde 400, 1 MiB üstü 413); /api/gorev denetle
#     için 'revize' alanı zorunlu JSON boolean (yoksa 400, sessiz onay yok).
#   * Kaynak denetimi: Host yalnız loopback adı + zorunlu gerçek port (403),
#     Origin varsa yalnız http scheme + doğrulanmış Host authority ile birebir
#     eşleşme ('null'/yabancı → 403), POST'ta Content-Type application/json
#     (aksi 415), OPTIONS'a CORS izni yok (405). Loopback dışı bind fail-closed
#     reddedilir; istemci adresi de loopback olmalı.
#     Bu filtre kimlik doğrulaması değildir. Görev yazımı ayrıca HMAC principal
#     ister; aynı UID ve eski kopyalar veri dosyalarına doğrudan yazabilir.
import errno
import fcntl
import contextlib
import heapq
import importlib.util
import io
import ipaddress
import json
import os
import random
import secrets
import sys
import tempfile
import threading
import time
import stat
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.machinery import SourceFileLoader
from pathlib import Path
from urllib.parse import urlsplit

CODE_ROOT = Path(__file__).resolve().parent.parent
KOK = Path(os.environ.get("YUVA_DIR") or (Path.home() / "yuva"))
DURUM = KOK / "durum.json"
GOREV = KOK / "gorevler.json"
BUS = KOK / "mesaj.jsonl"
EKRAN = KOK / "ekran"
KILIT_DOSYA = KOK / ".kilit"
DATA_SCHEMA_VERSION = 1
MESSAGE_SCHEMA_VERSIONS = frozenset({1, 2})
MESAJ_KAYNAK_SINIFLARI = frozenset({"operator", "agent", "unknown"})
CLI = CODE_ROOT / "bin" / "yuva"
_TASK_CORE = None
_TASK_CORE_LOCK = threading.Lock()


def _ekran_redaksiyon_modulu_yukle():
    path = CODE_ROOT / "yuva_screen_redaction.py"
    spec = importlib.util.spec_from_file_location("yuva_screen_redaction_panel", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("screen redaction module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_EKRAN_REDAKSIYON = _ekran_redaksiyon_modulu_yukle()
_SNAPSHOT_BUDGET = None
_SNAPSHOT_BUDGET_LOCK = threading.Lock()


def _snapshot_budget_modulu_yukle():
    """Load the production selector only when its feature gate is enabled."""
    global _SNAPSHOT_BUDGET
    with _SNAPSHOT_BUDGET_LOCK:
        if _SNAPSHOT_BUDGET is None:
            path = CODE_ROOT / "panel" / "snapshot_budget.py"
            spec = importlib.util.spec_from_file_location(
                "yuva_panel_snapshot_budget", path)
            if spec is None or spec.loader is None:
                raise RuntimeError("snapshot budget module unavailable")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(spec.name, None)
                raise
            _SNAPSHOT_BUDGET = module
        return _SNAPSHOT_BUDGET

ONLINE_SN = 30        # son kalp atışı bu süreden taze ise model çevrimiçi
MESAJ_SN = 200        # /api/veri'de dönen mesaj sayısı
EKRAN_SN = 60         # model başına dönen ekran satırı
EKRAN_DOSYA_AZAMI = 128  # /api/veri için bir round-robin sayfasındaki dosya sayısı
EKRAN_TARAMA_TOPLAM_BAYT = 8 * 1024 * 1024  # tüm dosyalardaki ham JSONL okuma bütçesi
EKRAN_PARSE_TOPLAM_BAYT = 2 * 1024 * 1024  # json.loads'a verilen toplam kayıt baytı
EKRAN_CIKTI_TOPLAM_BAYT = 2 * 1024 * 1024  # ekranlar alanının JSON kodlu üst sınırı
SNAPSHOT_DURUM_KAYNAK_BAYT_AZAMI = 4 * 1024 * 1024
SNAPSHOT_GOREV_KAYNAK_BAYT_AZAMI = 16 * 1024 * 1024
_EKRAN_SECIM_KILIT = threading.Lock()
_EKRAN_SECIM_KURSORU = None
GOVDE_SINIR = 1024 * 1024   # POST gövdesi üst sınırı (bayt); aşan istek gövdesi okunmadan 413
SNAPSHOT_BUDGET_ENV = "YUVA_SNAPSHOT_BUDGET_ENABLED"
BROWSER_GET_ROUTE_POLICY = {
    "/": "browser.shell",
    "/index.html": "browser.shell",
    "/api/veri": "snapshot.read",
    "/veri": "snapshot.read",
}
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


class SnapshotSourceLimit(RuntimeError):
    """Snapshot input exceeded its parse-before-read byte ceiling."""

    def __init__(self, source, limit_bytes):
        self.source = source
        self.limit_bytes = limit_bytes
        super().__init__("snapshot source limit exceeded")


def browser_get_route(target):
    """Classify only exact browser GET targets; return malformed aliases separately."""
    if target in BROWSER_GET_ROUTE_POLICY:
        return target, False
    path = target.split("?", 1)[0]
    candidate = path.rstrip("/") or "/"
    if candidate in BROWSER_GET_ROUTE_POLICY:
        return None, True
    return None, False


def _schema_version_kontrolu(veri, dosya_adi, desteklenen):
    version = veri.get("schema_version", 1)
    if type(version) is not int or version not in desteklenen:
        raise DurumHatasi(
            f"{dosya_adi}: desteklenmeyen schema_version; veri değiştirilmedi")


def _guvenli_hata_kaydi(context, error):
    """Log bounded diagnostics only; exception text may contain user data/secrets."""
    kind = type(error).__name__
    if (not kind or len(kind) > 48
            or not kind.isascii() or not kind.replace("_", "").isalnum()):
        kind = "Exception"
    cause = getattr(error, "__cause__", None)
    number = getattr(error, "errno", None)
    if type(number) is not int and cause is not None:
        number = getattr(cause, "errno", None)
    if type(number) is not int or not 0 <= number <= 999:
        number = "-"
    event_id = secrets.token_hex(4)
    print(f"yuva-panel error id={event_id} context={context} type={kind} errno={number}",
          file=sys.stderr, flush=True)
    return event_id


# Süreçler arası kilit: CLI (bin/yuva -> ekle_jsonl) ile AYNI dosya (KOK/.kilit).
# Görev köprüsü ayrı panel kilidi tutmaz; görev core'u kendi atomik kilitlerini
# ve JSONL append kilidini kullanır.
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
        self._fd = None
        self._kok_fd = None

    def __enter__(self):
        derinlik = getattr(_kilit_yerel, "derinlik", 0)
        if derinlik == 0:
            kok_fd = None
            fd = None
            try:
                kok_fd = guvenli_dizin_fd(KOK, olustur=True)
                bayraklar = (os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
                             | getattr(os, "O_CLOEXEC", 0))
                for _ in range(3):
                    try:
                        fd = os.open(".kilit", bayraklar, dir_fd=kok_fd)
                        break
                    except FileNotFoundError:
                        try:
                            fd = os.open(".kilit", bayraklar | os.O_CREAT | os.O_EXCL,
                                         0o600, dir_fd=kok_fd)
                            break
                        except FileExistsError:
                            continue
                if fd is None:
                    raise OSError("kilit dosyası oluşturma yarışı")
                bilgi = os.fstat(fd)
                if (not stat.S_ISREG(bilgi.st_mode) or bilgi.st_uid != os.geteuid()
                        or stat.S_IMODE(bilgi.st_mode) != 0o600 or bilgi.st_nlink != 1):
                    raise DurumHatasi(
                        "durum kilidi güvenli değil (tür/sahip/izin/link reddedildi)")
            except OSError as e:
                if fd is not None:
                    os.close(fd)
                if kok_fd is not None:
                    os.close(kok_fd)
                raise DurumHatasi(f"durum kilidi açılamadı ({KILIT_DOSYA}): {e}") from e
            except BaseException:
                if fd is not None:
                    os.close(fd)
                if kok_fd is not None:
                    os.close(kok_fd)
                raise
            try:
                bitis = time.monotonic() + self.sn
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic() >= bitis:
                            raise DurumHatasi(
                                f"durum kilidi alınamadı ({KILIT_DOSYA}, {self.sn:g} sn bekledi)")
                        time.sleep(0.05)
                try:
                    yol_bilgi = os.stat(".kilit", dir_fd=kok_fd, follow_symlinks=False)
                except OSError as e:
                    raise DurumHatasi(
                        f"durum kilidi yolu kilit sonrası doğrulanamadı: {e}") from e
                fd_bilgi = os.fstat(fd)
                if ((fd_bilgi.st_dev, fd_bilgi.st_ino)
                        != (yol_bilgi.st_dev, yol_bilgi.st_ino)
                        or not stat.S_ISREG(yol_bilgi.st_mode)
                        or yol_bilgi.st_uid != os.geteuid()
                        or stat.S_IMODE(yol_bilgi.st_mode) != 0o600
                        or yol_bilgi.st_nlink != 1):
                    raise DurumHatasi(
                        "durum kilidi yolu, kilit fd'siyle eşleşmiyor veya güvenli değil")
            except BaseException:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(fd)
                os.close(kok_fd)
                raise
            self._fd = fd
            self._kok_fd = kok_fd
        _kilit_yerel.derinlik = derinlik + 1
        return self

    def __exit__(self, *exc):
        _kilit_yerel.derinlik = max(0, getattr(_kilit_yerel, "derinlik", 1) - 1)
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                os.close(self._kok_fd)
        return False


_YOK = object()          # oku(): "dosya yok/boş" ile geçerli JSON `null` ayrımı için


ROLLER = ("goreci", "isci", "denetci")
ROL_AD = {"goreci": "görevli", "isci": "işçi", "denetci": "denetçi"}
ARACLAR = ("claude", "codex", "opencode", "diger")
TURLER = ("not", "soru", "cevap", "rapor", "denetim", "gorev", "durum")
EKRAN_TURLERI = ("ekran", "komut", "sonuc", "baslik")
MESAJ_REZERVE_ALANLAR = frozenset({
    "schema_version", "actor_id", "source", "trust", "auth_method",
    "provenance", "source_class", "source_class_trust", "kanal", "id", "message_id", "ts",
    "kimlik", "principal_id", "operation_id", "epoch", "verified",
    "correlation_id", "task_id", "workflow_id", "dispatch",
})
MESAJ_SNAPSHOT_ALANLARI = (
    "id", "ts", "kimden", "ad", "kime", "metin", "tur",
    "source_class", "source_class_trust", "provenance",
)
GOREV_SNAPSHOT_ALANLARI = (
    "id", "baslik", "detay", "durum", "kimden", "assignee",
    "gorevli_kimlik", "inceleyen_kimlik", "ust_gorev_id", "gecmis",
)
GOREV_DURUMLARI = frozenset({
    "pending", "assigned", "pending_gorevli_review",
    "pending_verification", "verified", "pending_revision", "dropped",
})
GOREV_OLAY_SNAPSHOT_ALANLARI = (
    "ts", "kimden", "olay", "not", "actor_trust", "rol", "role",
)


# ── yardımcılar ───────────────────────────────────────────────────────

def simdi():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def uid():
    return f"{int(time.time() * 1000):x}-{random.randint(1000, 9999)}"


AUTH_MESAJ_SCOPELARI = frozenset({
    "POST /api/katil", "POST /api/ayril", "POST /api/ad", "POST /api/rol",
    "POST /api/yaz", "POST /api/sorumlu", "POST /api/bas-denetci",
})


def hmac_zarf_gecerli(m):
    """Validate server envelope shape; same-UID JSONL can still forge it."""
    p = m.get("provenance") if isinstance(m, dict) else None
    claim = p.get("identity_claim") if isinstance(p, dict) else None
    if not isinstance(p, dict) or not isinstance(claim, dict):
        return False
    actor = p.get("actor_id")

    def valid_id(value):
        return (isinstance(value, str) and 1 <= len(value) <= 128
                and value[0].isascii() and value[0].isalnum()
                and all(c.isascii() and (c.isalnum() or c in "._:@-")
                        for c in value))

    temel = (
        m.get("schema_version") == 2
        and m.get("source") == "panel_api" and p.get("source") == "panel_api"
        and m.get("trust") == "verified" and p.get("trust") == "verified"
        and m.get("actor_id") == actor and m.get("kimden") == actor
        and m.get("auth_method") == "hmac-sha256"
        and p.get("auth_method") == "hmac-sha256"
        and valid_id(actor) and valid_id(p.get("key_id"))
        and valid_id(p.get("audience"))
        and isinstance(p.get("scope"), str)
        and p.get("scope") in AUTH_MESAJ_SCOPELARI
        and type(p.get("timestamp")) is int
        and 0 <= p["timestamp"] <= 253402300799
        and claim.get("value") == actor
        and claim.get("source") == "hmac_principal"
        and claim.get("trust") == "verified"
        and claim.get("actor_id") == actor
        and set(p) == {"source", "trust", "actor_id", "auth_method",
                       "identity_claim", "key_id", "audience", "scope", "timestamp"}
        and set(claim) == {"value", "source", "trust", "actor_id"}
        and isinstance(m.get("id"), str) and isinstance(m.get("ts"), str)
        and isinstance(m.get("metin"), str)
    )
    if not temel:
        return False
    if m.get("kanal") == "audit":
        audit = m.get("audit")
        return (m.get("tur") == "denetim" and isinstance(audit, dict)
                and set(m) == {"id", "ts", "kimden", "kime", "tur", "metin", "ad",
                               "kanal", "schema_version", "source", "trust", "actor_id",
                               "auth_method", "provenance", "audit"}
                and set(audit) == {"event_id", "operation", "target_id", "before", "after"}
                and audit.get("event_id") == m.get("id")
                and isinstance(audit.get("operation"), str)
                and audit.get("operation") in {"sorumlu.set", "bas_denetci.set"}
                and valid_id(audit.get("target_id"))
                and all(value is None or valid_id(value)
                        for value in (audit.get("before"), audit.get("after")))
                and m.get("kimden") == actor)
    chat_fields = {"id", "ts", "kimden", "kime", "tur", "metin", "ad",
                   "kanal", "schema_version", "source", "trust", "actor_id",
                   "auth_method", "provenance"}
    enriched_chat_fields = chat_fields | {"source_class", "source_class_trust"}
    return (m.get("kanal") == "sohbet" and m.get("tur") in TURLER
            and (set(m) == chat_fields or set(m) == enriched_chat_fields)
            and (set(m) == chat_fields or
                 (m.get("source_class") in MESAJ_KAYNAK_SINIFLARI
                  and m.get("source_class_trust") == "unverified")))


def oku(p, varsayilan, *, bos_varsayilan=True):
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
        if not bos_varsayilan:
            raise DurumHatasi(f"{p.name} boş JSON; dosya değiştirilmedi")
        return varsayilan          # sıfır/boş dosya: yeni sayılır (kayıp veri yok)
    try:
        return json.loads(ham)
    except json.JSONDecodeError as e:
        raise DurumHatasi(
            f"{p.name} bozuk JSON (satır {e.lineno}, sütun {e.colno}: {e.msg}); "
            f"dosya değiştirilmedi, elle onarılmalı") from e


def oku_bayt_sinirli(p, varsayilan, limit_bayt, kaynak, *, bos_varsayilan=True):
    """Read and parse at most limit+1 bytes, rejecting growth or source drift."""
    p = Path(p)
    if type(limit_bayt) is not int or limit_bayt < 1:
        raise ValueError("snapshot source byte limit must be a positive integer")
    try:
        f = p.open("rb")
    except FileNotFoundError:
        return varsayilan
    except OSError as e:
        raise DurumHatasi(f"{p.name} okunamadı ({type(e).__name__})") from None
    try:
        with f:
            before = os.fstat(f.fileno())
            raw = bytearray()
            remaining = limit_bayt + 1
            while remaining > 0:
                chunk = f.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                raw.extend(chunk)
                remaining -= len(chunk)
            after = os.fstat(f.fileno())
    except OSError as e:
        raise DurumHatasi(f"{p.name} okunamadı ({type(e).__name__})") from None

    if (before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_size,
            after.st_mtime_ns, after.st_ctime_ns):
        raise DurumHatasi(f"{p.name} snapshot okunurken değişti")
    if len(raw) > limit_bayt:
        raise SnapshotSourceLimit(kaynak, limit_bayt)
    if not raw.strip():
        if not bos_varsayilan:
            raise DurumHatasi(f"{p.name} boş JSON; dosya değiştirilmedi")
        return varsayilan
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise DurumHatasi(f"{p.name} okunamadı (kodlama hatası): {e}") from None
    try:
        return json.loads(decoded)
    except json.JSONDecodeError as e:
        raise DurumHatasi(
            f"{p.name} bozuk JSON (satır {e.lineno}, sütun {e.colno}: {e.msg}); "
            "dosya değiştirilmedi, elle onarılmalı") from e
    except RecursionError:
        raise DurumHatasi(f"{p.name} JSON nesting limitini aştı") from None


def yaz(p, v):
    """Dayanıklı atomik yazma: geçici dosya + os.replace + üst dizin fsync.

    Sabit adlı `.tmp` kullanılmaz (eşzamanlı yazımlarda birbirini ezerdi).
    Geçici dosya hedefin izin maskesini devralır; hata halinde artık bırakılmaz.
    """
    p = Path(p)
    if p == DURUM:
        if not isinstance(v, dict):
            raise DurumHatasi(f"{p.name}: JSON nesnesi gerekli")
        _schema_version_kontrolu(v, p.name, {DATA_SCHEMA_VERSION})
        v.setdefault("schema_version", DATA_SCHEMA_VERSION)
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
    try:
        relative = yol.relative_to(KOK)
    except ValueError as e:
        raise DurumHatasi("JSONL yolu Yuva veri kökünün dışında") from e
    if len(relative.parts) == 1 and relative.name == BUS.name:
        alt_dizin = None
        dosya_adi = relative.name
    elif (len(relative.parts) == 2 and relative.parts[0] == EKRAN.name
          and relative.name.endswith(".jsonl")):
        alt_dizin = EKRAN.name
        dosya_adi = relative.name
    else:
        raise DurumHatasi("desteklenmeyen JSONL yolu")
    if alt_dizin == EKRAN.name:
        satir = _EKRAN_REDAKSIYON.redact_screen_record(satir)
    payload = (json.dumps(satir, ensure_ascii=False) + "\n").encode("utf-8")
    kontrol_fd = guvenli_dizin_fd(KOK, olustur=True)
    os.close(kontrol_fd)
    with dosya_kilidi():
        kok_fd = guvenli_dizin_fd(KOK, olustur=True)
        try:
            parent_fd = (guvenli_alt_dizin_fd(kok_fd, alt_dizin, olustur=True)
                         if alt_dizin else os.dup(kok_fd))
            try:
                flags = (os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW
                         | getattr(os, "O_CLOEXEC", 0)
                         | getattr(os, "O_NONBLOCK", 0))
                try:
                    fd = os.open(dosya_adi, flags | os.O_CREAT | os.O_EXCL,
                                 0o600, dir_fd=parent_fd)
                except FileExistsError:
                    fd = os.open(dosya_adi, flags, dir_fd=parent_fd)
                try:
                    jsonl_fd_dogrula(fd, dosya_adi)
                    kalan = memoryview(payload)
                    while kalan:
                        try:
                            yazilan = os.write(fd, kalan)
                        except InterruptedError:
                            continue
                        if yazilan <= 0:
                            raise OSError("JSONL append ilerlemedi")
                        kalan = kalan[yazilan:]
                finally:
                    os.close(fd)
            finally:
                os.close(parent_fd)
        finally:
            os.close(kok_fd)
    return satir


def _dizin_fd_aciklama():
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise DurumHatasi("güvenli JSONL için O_NOFOLLOW/O_DIRECTORY gerekli")
    return (os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0))


def _dizin_dogrula(fd, ad):
    bilgi = os.fstat(fd)
    if (not stat.S_ISDIR(bilgi.st_mode) or bilgi.st_uid != os.geteuid()
            or stat.S_IMODE(bilgi.st_mode) != 0o700):
        raise DurumHatasi(f"{ad} güvenli Yuva dizini değil (sahip/tür/izin reddedildi)")


def _ata_yolu_dogrula(fd, ad):
    bilgi = os.fstat(fd)
    kip = stat.S_IMODE(bilgi.st_mode)
    sticky = bool(bilgi.st_mode & stat.S_ISVTX)
    if (not stat.S_ISDIR(bilgi.st_mode)
            or (kip & 0o022 and not sticky)):
        raise DurumHatasi(f"güvenli olmayan üst dizin: {ad}")


def guvenli_dizin_fd(yol, olustur=False):
    absolute = os.path.abspath(os.fspath(yol))
    if ".." in Path(absolute).parts:
        raise DurumHatasi("Yuva dizin yolu üst dizin bileşeni içeremez")
    parcalar = Path(absolute).parts
    fd = os.open(os.sep, _dizin_fd_aciklama())
    try:
        _ata_yolu_dogrula(fd, os.sep)
        for indeks, parca in enumerate(parcalar[1:]):
            try:
                yeni_fd = os.open(parca, _dizin_fd_aciklama(), dir_fd=fd)
            except FileNotFoundError:
                if not olustur:
                    raise
                try:
                    os.mkdir(parca, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                yeni_fd = os.open(parca, _dizin_fd_aciklama(), dir_fd=fd)
            try:
                son = indeks == len(parcalar[1:]) - 1
                if son:
                    _dizin_dogrula(yeni_fd, absolute)
                else:
                    _ata_yolu_dogrula(yeni_fd, parca)
            except BaseException:
                os.close(yeni_fd)
                raise
            eski_fd = fd
            fd = yeni_fd
            os.close(eski_fd)
        if len(parcalar) == 1:
            raise DurumHatasi("Yuva veri kökü filesystem root olamaz")
        return fd
    except BaseException:
        os.close(fd)
        raise


def guvenli_alt_dizin_fd(parent_fd, ad, olustur=False):
    try:
        fd = os.open(ad, _dizin_fd_aciklama(), dir_fd=parent_fd)
    except FileNotFoundError:
        if not olustur:
            raise
        try:
            os.mkdir(ad, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        fd = os.open(ad, _dizin_fd_aciklama(), dir_fd=parent_fd)
    try:
        _dizin_dogrula(fd, ad)
        return fd
    except BaseException:
        os.close(fd)
        raise


def jsonl_fd_dogrula(fd, ad):
    bilgi = os.fstat(fd)
    if (not stat.S_ISREG(bilgi.st_mode) or bilgi.st_uid != os.geteuid()
            or stat.S_IMODE(bilgi.st_mode) != 0o600 or bilgi.st_nlink != 1):
        raise DurumHatasi(f"{ad} güvenli JSONL dosyası değil (sahip/tür/izin/link reddedildi)")


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


def durum_oku(*, snapshot=False):
    """durum.json'u katı okur: eksik/boş dosya = boş durum, bozuk dosya = DurumHatasi."""
    d = (oku_bayt_sinirli(DURUM, _YOK, SNAPSHOT_DURUM_KAYNAK_BAYT_AZAMI,
                          "durum") if snapshot else oku(DURUM, _YOK))
    if d is _YOK:
        return {"kullanicilar": {}, "rev": 0}
    if not isinstance(d, dict):
        raise DurumHatasi(f"{DURUM.name} kökü JSON nesnesi değil")
    _schema_version_kontrolu(d, DURUM.name, {DATA_SCHEMA_VERSION})
    ks = d.setdefault("kullanicilar", {})
    if not isinstance(ks, dict):
        raise DurumHatasi(f"{DURUM.name}: 'kullanicilar' JSON nesnesi olmalı")
    d.setdefault("rev", 0)
    if type(d["rev"]) is not int or d["rev"] < 0:
        raise DurumHatasi(f"{DURUM.name}: 'rev' negatif olmayan tamsayı olmalı")
    return d


def gorev_oku(*, snapshot=False):
    """Görev defterinde eksik dosya boş sayılır; boş/bozuk kayıt fail-closed."""
    g = (oku_bayt_sinirli(GOREV, _YOK, SNAPSHOT_GOREV_KAYNAK_BAYT_AZAMI,
                          "gorevler", bos_varsayilan=False)
         if snapshot else oku(GOREV, _YOK, bos_varsayilan=False))
    if g is _YOK:
        return {"siradaki": 1, "gorevler": []}
    if not isinstance(g, dict):
        raise DurumHatasi(f"{GOREV.name} kökü JSON nesnesi değil")
    _schema_version_kontrolu(g, GOREV.name, {DATA_SCHEMA_VERSION})
    gs = g.setdefault("gorevler", [])
    if not isinstance(gs, list):
        raise DurumHatasi(f"{GOREV.name}: 'gorevler' liste olmalı")
    s = g.setdefault("siradaki", 1)
    if isinstance(s, bool) or not isinstance(s, int):
        raise DurumHatasi(f"{GOREV.name}: 'siradaki' tamsayı olmalı")
    gorev_idleri = set()
    for gorev in gs:
        if not isinstance(gorev, dict):
            raise DurumHatasi(f"{GOREV.name}: görev kaydı nesne olmalı")
        gid = gorev.get("id")
        if isinstance(gid, bool) or not isinstance(gid, int) or gid < 1:
            raise DurumHatasi(
                f"{GOREV.name}: görev ID'si kanonik pozitif tamsayı değil")
        if gid in gorev_idleri:
            raise DurumHatasi(f"{GOREV.name}: görev ID'si tekil değil: #{gid}")
        gorev_idleri.add(gid)
        durum = gorev.get("durum")
        if not isinstance(durum, str) or durum not in GOREV_DURUMLARI:
            raise DurumHatasi(
                f"{GOREV.name}: görev durumu geçerli bir metin durumu değil")
        history = gorev.get("gecmis", [])
        if not isinstance(history, list):
            raise DurumHatasi(f"{GOREV.name}: görev geçmişi liste olmalı")
        if any(not isinstance(event, dict) for event in history):
            raise DurumHatasi(f"{GOREV.name}: geçmiş olayı nesne olmalı")
    return g


def durum_yaz(d):
    _schema_version_kontrolu(d, DURUM.name, {DATA_SCHEMA_VERSION})
    d.setdefault("schema_version", DATA_SCHEMA_VERSION)
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


def mesaj_ekle(kimden, metin, kime="@hepsi", tur="not", ad=None, kanal="sohbet",
               kaynak="panel_server", kimlik_iddiasi=None, principal=None,
               source_class="unknown", source_class_trust="unverified"):
    if source_class not in MESAJ_KAYNAK_SINIFLARI:
        source_class = "unknown"
    if principal is not None:
        # A verified principal is passed out-of-band; body display claims never
        # choose the authenticated writer identity.
        kimden = principal.principal_id
        kimlik_iddiasi = principal.principal_id
        ad = ad or kimden
    if principal is not None:
        provenance = {
            "source": "panel_api", "trust": "verified",
            "actor_id": principal.principal_id, "auth_method": "hmac-sha256",
            "identity_claim": {"value": principal.principal_id,
                               "source": "hmac_principal", "trust": "verified",
                               "actor_id": principal.principal_id},
            "key_id": principal.key_id, "audience": principal.audience,
            "scope": principal.scope, "timestamp": principal.timestamp,
        }
        kaynak = "panel_api"
    else:
        provenance = {
            "source": kaynak, "trust": "unverified", "actor_id": None,
            "auth_method": "none",
            "identity_claim": {
                "value": str(kimlik_iddiasi if kimlik_iddiasi is not None else kimden),
                "source": "unknown", "trust": "unverified", "actor_id": None,
            },
        }
    m = {"id": uid(), "ts": simdi(), "kimden": kimden, "kime": kime or "@hepsi",
         "tur": tur if tur in TURLER else "not", "metin": metin,
         "ad": ad or kimden, "kanal": kanal, "schema_version": 2,
         "source": kaynak, "trust": provenance["trust"],
         "actor_id": provenance["actor_id"],
         "auth_method": provenance["auth_method"], "provenance": provenance}
    if kanal == "sohbet":
        m["source_class"] = source_class
        m["source_class_trust"] = ("verified" if source_class_trust == "verified"
                                    and principal is not None else "unverified")
    ekle(BUS, m)
    return m


def admin_mutasyon_audit_ekle(islem, hedef, onceki, sonraki, principal=None):
    """Append one successful admin-mutation event to the shared message JSONL.

    The event is not atomic with durum.json. A failed append can follow a
    committed state mutation; callers must report that ambiguity explicitly.
    """
    actor_id = principal.principal_id if principal is not None else None
    zarf = {
        "source": "panel_api", "trust": "unverified", "actor_id": None,
        "auth_method": "none",
        "identity_claim": {"value": "unknown", "source": "unknown",
                           "trust": "unverified", "actor_id": None},
    }
    if principal is not None:
        zarf = {
            "source": "panel_api", "trust": "verified", "actor_id": actor_id,
            "auth_method": "hmac-sha256",
            "identity_claim": {"value": actor_id, "source": "hmac_principal",
                               "trust": "verified", "actor_id": actor_id},
            "key_id": principal.key_id, "audience": principal.audience,
            "scope": principal.scope, "timestamp": principal.timestamp,
        }
    event_id = uid()
    event = {
        "id": event_id, "ts": simdi(), "kimden": actor_id or "unknown",
        "kime": "@hepsi", "tur": "denetim",
        "metin": f"Yönetim mutasyonu: {islem}",
        "ad": actor_id or "Doğrulanmamış kaynak", "kanal": "audit",
        "schema_version": 2, "source": "panel_api",
        "trust": zarf["trust"], "actor_id": actor_id,
        "auth_method": zarf["auth_method"], "provenance": zarf,
        "audit": {"event_id": event_id, "operation": islem,
                  "target_id": hedef, "before": onceki, "after": sonraki},
    }
    ekle(BUS, event)
    return event


def jsonl_tail_satirlari(yol, en_cok_satir, en_cok_bayt, en_cok_kayit_bayt,
                         taranan_dondur=False, istatistik=None):
    """Dosyanın sonundaki LF ile tamamlanmış, bütçeli JSONL satırlarını oku."""
    if istatistik is not None:
        istatistik.update(bytes_scanned=0, byte_budget_exhausted=False,
                          row_limit_exceeded=False, oversized_records=0)
    if en_cok_satir <= 0 or en_cok_bayt <= 0 or en_cok_kayit_bayt <= 0:
        return ([], 0) if taranan_dondur else []
    parcalar = []
    taranan = 0
    lf_sayisi = 0
    with open(yol, "rb") as f:
        cursor = os.fstat(f.fileno()).st_size
        while cursor > 0 and taranan < en_cok_bayt and lf_sayisi < en_cok_satir + 1:
            boyut = min(8192, cursor, en_cok_bayt - taranan)
            cursor -= boyut
            f.seek(cursor)
            parca = f.read(boyut)
            if len(parca) != boyut:
                raise OSError("JSONL boyutu okunurken değişti")
            parcalar.append(parca)
            taranan += boyut
            lf_sayisi += parca.count(b"\n")
    if istatistik is not None:
        istatistik["bytes_scanned"] = taranan
        istatistik["byte_budget_exhausted"] = (
            cursor > 0 and taranan >= en_cok_bayt
            and lf_sayisi < en_cok_satir + 1)
    veri = b"".join(reversed(parcalar))
    if cursor > 0:
        sinir = veri.find(b"\n")
        if sinir < 0:
            if istatistik is not None:
                istatistik["byte_budget_exhausted"] = True
            return ([], taranan) if taranan_dondur else []
        veri = veri[sinir + 1:]
    if veri and not veri.endswith(b"\n"):
        son_lf = veri.rfind(b"\n")
        veri = veri[:son_lf + 1] if son_lf >= 0 else b""
    satirlar = veri.split(b"\n")
    if satirlar and satirlar[-1] == b"":  # son LF kayıt ayıracıdır
        satirlar.pop()
    if istatistik is not None:
        istatistik["row_limit_exceeded"] = len(satirlar) > en_cok_satir
    sonuc = []
    for satir in satirlar[-en_cok_satir:]:
        if satir and len(satir) <= en_cok_kayit_bayt:
            sonuc.append(satir.decode("utf-8", errors="replace"))
        elif satir and istatistik is not None:
            istatistik["oversized_records"] += 1
    return (sonuc, taranan) if taranan_dondur else sonuc


def mesajlar(n=MESAJ_SN):
    if not BUS.exists():
        return []
    try:
        n = max(1, min(int(n), MESAJ_SN))
        satirlar = jsonl_tail_satirlari(
            BUS, en_cok_satir=n * 3, en_cok_bayt=2 * 1024 * 1024,
            en_cok_kayit_bayt=64 * 1024)
    except Exception:
        return []
    ms = []
    for s in satirlar:
        try:
            m = json.loads(s)
        except Exception:
            continue
        if not isinstance(m, dict):
            continue
        if "schema_version" in m and (
                type(m["schema_version"]) is not int
                or m["schema_version"] not in MESSAGE_SCHEMA_VERSIONS):
            continue  # bilinmeyen şema legacy kabul edilmez ve yetki kazanmaz
        m = dict(m)
        if hmac_zarf_gecerli(m):
            zarf = m["provenance"]
            m.update(source="panel_api", trust="verified",
                     actor_id=zarf["actor_id"], auth_method="hmac-sha256",
                     provenance={k: zarf[k] for k in (
                         "source", "trust", "actor_id", "auth_method",
                         "identity_claim", "key_id", "audience", "scope", "timestamp")})
            _source_class_normalize(m)
            projected = _mesaj_snapshot_proje(m)
            if projected is not None:
                ms.append(projected)
            continue
        zarf = m.get("provenance")
        kimlik_zarfi = zarf.get("identity_claim") if isinstance(zarf, dict) else None
        zarf_gecerli = (
            m.get("schema_version") == 2
            and isinstance(zarf, dict)
            and isinstance(zarf.get("source"), str)
            and bool(zarf.get("source", "").strip())
            and zarf.get("trust") == "unverified"
            and zarf.get("actor_id") is None
            and zarf.get("auth_method") == "none"
            and isinstance(kimlik_zarfi, dict)
            and isinstance(kimlik_zarfi.get("value"), str)
            and kimlik_zarfi.get("source") == "unknown"
            and kimlik_zarfi.get("trust") == "unverified"
            and kimlik_zarfi.get("actor_id") is None
        )
        if zarf_gecerli:
            kaynak = zarf["source"]
            iddia = kimlik_zarfi["value"]
        else:
            # Legacy/eksik/kısmen bozuk zarfı arşivde değiştirmeden yalnız
            # okuma görünümünde unknown/unverified olarak normalize et.
            if m.get("schema_version") != 2:
                m["schema_version"] = 1
            kaynak = "unknown"
            iddia = (kimlik_zarfi.get("value") if isinstance(kimlik_zarfi, dict)
                     else m.get("kimden", "unknown"))
            if not isinstance(iddia, str):
                iddia = str(iddia)
        kimlik_iddiasi = {
            "value": str(iddia), "source": "unknown",
            "trust": "unverified", "actor_id": None,
        }
        provenance = {
            "source": kaynak,
            "trust": "unverified",
            "actor_id": None,
            "auth_method": "none",
            "identity_claim": kimlik_iddiasi,
        }
        m.update(schema_version=m.get("schema_version", 1),
                 source=kaynak, trust="unverified", actor_id=None,
                 auth_method="none", provenance=provenance)
        _source_class_normalize(m)
        projected = _mesaj_snapshot_proje(m)
        if projected is not None:
            ms.append(projected)
    return ms[-n:]


def _source_class_normalize(message):
    """Preserve valid class labels only as claims; old rows become unknown."""
    claimed = message.get("source_class")
    message["source_class"] = (claimed if isinstance(claimed, str)
                               and claimed in MESAJ_KAYNAK_SINIFLARI else "unknown")
    message["source_class_trust"] = "unverified"


def _mesaj_snapshot_proje(message):
    """Allowlist UI message fields and redact known secret forms on read."""
    projected = {key: message[key] for key in MESAJ_SNAPSHOT_ALANLARI
                 if key in message}
    text = projected.get("metin")
    if not isinstance(text, str):
        return None
    provenance = projected.get("provenance")
    if isinstance(provenance, dict):
        provenance = {key: provenance[key] for key in (
            "source", "trust", "actor_id", "auth_method", "identity_claim")
                      if key in provenance}
        identity = provenance.get("identity_claim")
        if isinstance(identity, dict):
            provenance["identity_claim"] = {
                key: identity[key] for key in ("value", "source", "trust", "actor_id")
                if key in identity
            }
        projected["provenance"] = provenance

    def redact_strings(value):
        if isinstance(value, str):
            return _EKRAN_REDAKSIYON.redact_text(value, max_bytes=64 * 1024)
        if isinstance(value, list):
            return [redact_strings(item) for item in value]
        if isinstance(value, dict):
            return {key: redact_strings(item) for key, item in value.items()}
        return value

    try:
        return redact_strings(projected)
    except Exception:
        return None


def _gorev_snapshot_proje(task):
    """Project documented task fields and event metadata for the panel UI."""
    projected = {key: task[key] for key in GOREV_SNAPSHOT_ALANLARI if key in task}
    history = projected.get("gecmis")
    if isinstance(history, list):
        projected["gecmis"] = [
            {key: event[key] for key in GOREV_OLAY_SNAPSHOT_ALANLARI if key in event}
            for event in history if isinstance(event, dict)
        ]
    return projected


def ekran_yaz(kimlik, ad, satir, tur="ekran", principal=None):
    if principal is not None:
        kimlik = principal.principal_id
        ad = ad or kimlik
    kayit = {"ts": simdi(), "kimlik": kimlik, "ad": ad,
             "tur": tur if tur in EKRAN_TURLERI else "ekran", "satir": satir}
    kayit = ekle(EKRAN / (guvenli(kimlik) + ".jsonl"), kayit)
    return kayit


def _ekran_dosya_sayfasi():
    """Select a lexical page without consuming files before they are read.

    Returns the cursor observed during selection. The caller commits progress
    only through the last file it actually considered, so a budget stop cannot
    skip the rest of a selected page.
    """
    with _EKRAN_SECIM_KILIT:
        cursor_before = _EKRAN_SECIM_KURSORU
        discovered = 0

        def after_cursor():
            nonlocal discovered
            for f in EKRAN.glob("*.jsonl"):
                discovered += 1
                if cursor_before is None or f.name > cursor_before:
                    yield f

        try:
            selected = heapq.nsmallest(EKRAN_DOSYA_AZAMI, after_cursor())
        except OSError:
            return [], discovered, True, cursor_before

        scan_error = False
        if cursor_before is not None and len(selected) < EKRAN_DOSYA_AZAMI:
            remaining = EKRAN_DOSYA_AZAMI - len(selected)
            try:
                wrapped = heapq.nsmallest(
                    remaining,
                    (f for f in EKRAN.glob("*.jsonl")
                     if f.name <= cursor_before),
                )
            except OSError:
                wrapped = []
                scan_error = True
            selected.extend(wrapped)

        return selected, discovered, scan_error, cursor_before


def _ekran_secim_ilerlet(cursor_before, last_considered):
    """Commit processed progress without overwriting a newer cursor."""
    global _EKRAN_SECIM_KURSORU
    if last_considered is None:
        return
    with _EKRAN_SECIM_KILIT:
        if _EKRAN_SECIM_KURSORU == cursor_before:
            _EKRAN_SECIM_KURSORU = last_considered


def tum_ekranlar(defer_cursor_commit=False):
    """Return a bounded screen map and metadata describing any partial result.

    Each call selects up to 128 filenames lexically after a process-local
    cursor, then wraps to the smallest names when needed. The cursor advances
    only through files actually considered, so budget stops leave later files
    eligible on a subsequent call. This round-robin order prevents a permanent
    first-page bias while the panel stays running;
    a panel restart resets selection to the first lexical page. The page is
    selected deterministically for its cursor and directory contents. The
    scan, parsed JSON input, and serialized ``ekranlar`` map have independent
    aggregate budgets. Whole-file rows remain included or omitted together
    when output space is insufficient, preserving the existing map value API.
    """
    out = {}
    if not EKRAN.exists():
        return out, {
            "partial": False, "files_discovered": 0, "files_considered": 0,
            "files_returned": 0,
            "file_limit": EKRAN_DOSYA_AZAMI,
            "selection_mode": "round_robin_lexicographic",
            "raw_bytes_scanned": 0, "raw_byte_budget_reserved": 0,
            "raw_byte_budget": EKRAN_TARAMA_TOPLAM_BAYT,
            "parsed_bytes": 0, "parsed_byte_budget": EKRAN_PARSE_TOPLAM_BAYT,
            "output_bytes": 2, "output_byte_budget": EKRAN_CIKTI_TOPLAM_BAYT,
            "partial_reasons": [],
        }

    reasons = set()
    kalan_tarama = EKRAN_TARAMA_TOPLAM_BAYT
    ham_bayt_okundu = 0
    parse_bayti = 0
    cikti_bayti = 2  # outer braces in json.dumps({})
    gorulen_dosya_sayisi = 0
    ele_alinan_dosya_sayisi = 0

    # Candidate memory stays bounded by one page. The server-local cursor
    # rotates pages over successive GET requests without changing the map API.
    try:
        dosyalar, gorulen_dosya_sayisi, scan_error, cursor_before = _ekran_dosya_sayfasi()
    except OSError:
        dosyalar, gorulen_dosya_sayisi = [], 0
        scan_error = True
        cursor_before = None
    if scan_error:
        reasons.add("directory_scan_error")
    if gorulen_dosya_sayisi > EKRAN_DOSYA_AZAMI:
        reasons.add("file_count_limit")

    last_considered = None
    for index, f in enumerate(dosyalar):
        if kalan_tarama <= 0:
            reasons.add("raw_byte_limit")
            break
        last_considered = f.name
        ele_alinan_dosya_sayisi += 1
        satirlar = []
        stats = {}
        try:
            boyut = f.stat().st_size
            ayrilan_bayt = min(1024 * 1024, kalan_tarama, boyut)
            kalan_tarama -= ayrilan_bayt  # reserve before reading, including error paths
            ham_satirlar, _ = jsonl_tail_satirlari(
                f, en_cok_satir=EKRAN_SN,
                en_cok_bayt=ayrilan_bayt,
                en_cok_kayit_bayt=16 * 1024, taranan_dondur=True,
                istatistik=stats)
            ham_bayt_okundu += stats.get("bytes_scanned", 0)
            if ayrilan_bayt < min(1024 * 1024, boyut):
                reasons.add("raw_byte_limit")
            if stats.get("byte_budget_exhausted"):
                reasons.add("raw_byte_limit")
            if stats.get("row_limit_exceeded"):
                reasons.add("per_file_row_limit")
            if stats.get("oversized_records", 0):
                reasons.add("record_size_limit")
            for s in reversed(ham_satirlar):
                satir_bayti = len(s.encode("utf-8"))
                if parse_bayti + satir_bayti > EKRAN_PARSE_TOPLAM_BAYT:
                    reasons.add("parsed_byte_limit")
                    break
                parse_bayti += satir_bayti
                try:
                    kayit = json.loads(s)
                except Exception:
                    reasons.add("invalid_record")
                    continue
                if not isinstance(kayit, dict):
                    reasons.add("invalid_record")
                    continue
                try:
                    # Legacy rows are redacted and allowlisted before they can
                    # consume output budget or enter the response snapshot.
                    satirlar.append(_EKRAN_REDAKSIYON.redact_screen_record(kayit))
                except Exception:
                    reasons.add("redaction_error")
        except Exception:
            reasons.add("read_error")
            continue
        satirlar.reverse()
        if satirlar:
            # Match the server's json.dumps(ensure_ascii=False) representation,
            # including map key and separators, before accepting this file.
            try:
                parca = (json.dumps(f.stem, ensure_ascii=False) + ": "
                         + json.dumps(satirlar, ensure_ascii=False))
                ek_bayt = len(parca.encode("utf-8")) + (2 if out else 0)
            except (UnicodeError, ValueError, TypeError, RecursionError):
                reasons.add("serialization_error")
            else:
                if cikti_bayti + ek_bayt > EKRAN_CIKTI_TOPLAM_BAYT:
                    reasons.add("output_byte_limit")
                    continue
                out[f.stem] = satirlar
                cikti_bayti += ek_bayt
        if "parsed_byte_limit" in reasons:
            break
        if kalan_tarama <= 0 and index + 1 < len(dosyalar):
            reasons.add("raw_byte_limit")
            break

    if not defer_cursor_commit:
        _ekran_secim_ilerlet(cursor_before, last_considered)

    meta = {
        "partial": bool(reasons),
        "files_discovered": gorulen_dosya_sayisi,
        "files_considered": ele_alinan_dosya_sayisi,
        "files_returned": len(out),
        "file_limit": EKRAN_DOSYA_AZAMI,
        "selection_mode": "round_robin_lexicographic",
        "raw_bytes_scanned": ham_bayt_okundu,
        "raw_byte_budget_reserved": EKRAN_TARAMA_TOPLAM_BAYT - kalan_tarama,
        "raw_byte_budget": EKRAN_TARAMA_TOPLAM_BAYT,
        "parsed_bytes": parse_bayti,
        "parsed_byte_budget": EKRAN_PARSE_TOPLAM_BAYT,
        "output_bytes": cikti_bayti,
        "output_byte_budget": EKRAN_CIKTI_TOPLAM_BAYT,
        "partial_reasons": sorted(reasons),
    }
    if defer_cursor_commit:
        meta["_cursor_before"] = cursor_before
        meta["_last_considered"] = last_considered
    return out, meta


# ── API uçları ────────────────────────────────────────────────────────

def api_katil(g, principal=None):
    kimlik = (principal.principal_id if principal is not None
              else str(g.get("kimlik") or "").strip())
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
        # Kayıt isteği son_gorulme/son_kalp kanıtı değildir.
        if not zaten_bagli:
            v.pop("son_kalp", None)
        ad = adi(kimlik, v)
        if not v.get("duyuruldu"):
            v["duyuruldu"] = True
            mesaj_ekle(kimlik, f"🟢 {ad} bağlandı (arac: {arac}, rol: {ROL_AD[rol]})",
                       tur="durum", ad=ad, principal=principal)
        durum_yaz(d)
    return 200, {"ok": True, "kimlik": kimlik, "ad": ad, "rol": rol,
                 "bas_denetci": bool(v.get("bas_denetci"))}


def api_kalp(g, principal=None):
    # Bu panelde doğrulanmış broker principal'ı yoktur. İstemci kimliği veya
    # loopback erişimi heartbeat yetkisi sayılmaz; G1/W1b gelene dek salt ret.
    return 503, {"ok": False, "hata": "doğrulanmış heartbeat kaynağı yok",
                 "online": False}


def api_ayril(g, principal=None):
    kimlik = (principal.principal_id if principal is not None
              else str(g.get("kimlik") or "").strip())
    with KILIT, dosya_kilidi():
        d = durum_oku()
        k = coz(d, kimlik)
        if not k:
            return 400, {"ok": False, "hata": f"bilinmeyen kimlik: {kimlik}"}
        v = d["kullanicilar"][k]
        v["bagli"] = False
        v["duyuruldu"] = False
        durum_yaz(d)
        mesaj_ekle(k, f"⚫ {adi(k, v)} ayrıldı", tur="durum", ad=adi(k, v),
                   principal=principal)
    return 200, {"ok": True, "kimlik": k}


def api_ad(g, principal=None):
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
            actor_id = principal.principal_id if principal is not None else k
            actor = d["kullanicilar"].get(actor_id, {})
            actor_ad = adi(actor_id, actor) if principal is not None else v["ad"]
            mesaj_ekle(actor_id, f"🏷️ {eski} → {v['ad']} adını aldı",
                       tur="durum", ad=actor_ad, principal=principal)
    return 200, {"ok": True, "kimlik": k, "ad": v["ad"]}


def api_rol(g, principal=None):
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
        actor_id = principal.principal_id if principal is not None else k
        actor = d["kullanicilar"].get(actor_id, {})
        actor_ad = adi(actor_id, actor) if principal is not None else adi(k, v)
        mesaj_ekle(actor_id, f"🎖️ {adi(k, v)} artık {ROL_AD[rol]}{ek}",
                   tur="durum", ad=actor_ad, principal=principal)
    return 200, {"ok": True, "kimlik": k, "ad": adi(k, v), "rol": rol,
                 "bas_denetci": v["bas_denetci"]}


def api_sorumlu(g, principal=None):
    """Set team ownership; identity exists only when the optional auth gate passes."""
    kimlik = str(g.get("kimlik") or "").strip()
    if not kimlik or "sorumlu_kimlik" not in g:
        return 400, {"ok": False, "hata": "kimlik ve sorumlu_kimlik alanları gerekli"}
    with KILIT, dosya_kilidi():
        d = durum_oku()
        k = coz(d, kimlik)
        if not k:
            return 400, {"ok": False, "hata": f"bilinmeyen kimlik: {kimlik}"}
        v = d["kullanicilar"][k]
        onceki = v.get("sorumlu_kimlik")
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
        try:
            admin_mutasyon_audit_ekle("sorumlu.set", k, onceki, sonuc, principal)
        except Exception:
            return 503, {"ok": False,
                         "hata": "mutasyon_kaydedildi_audit_durumu_belirsiz",
                         "mutasyon_kaydedildi": True, "audit_durumu": "belirsiz"}
    return 200, {"ok": True, "kimlik": k, "sorumlu_kimlik": sonuc}


def api_bas_denetci(g, principal=None):
    """Tek baş denetçiyi ata/kaldır; `etkin` JSON boolean olmalıdır.

    Actor principal is available only when the optional auth gate passes.
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
        onceki = next((x for x, v in d["kullanicilar"].items()
                       if v.get("bas_denetci")), None)
        hata = bas_denetci_ata(d, k, etkin)
        if hata:
            return 409, {"ok": False, "hata": hata}
        durum_yaz(d)
        secili = next((x for x, v in d["kullanicilar"].items()
                       if v.get("bas_denetci")), None)
        try:
            admin_mutasyon_audit_ekle("bas_denetci.set", k, onceki, secili, principal)
        except Exception:
            return 503, {"ok": False,
                         "hata": "mutasyon_kaydedildi_audit_durumu_belirsiz",
                         "mutasyon_kaydedildi": True, "audit_durumu": "belirsiz"}
    return 200, {"ok": True, "bas_denetci": secili}


def api_yaz(g, principal=None, authorization=None):
    rezerve = sorted(MESAJ_REZERVE_ALANLAR.intersection(g))
    if rezerve:
        return 400, {"ok": False,
                     "hata": "sunucu tarafından belirlenen alanlar gönderilemez: "
                             + ", ".join(rezerve)}
    metin = str(g.get("metin") or "").strip()
    if not metin:
        return 400, {"ok": False, "hata": "metin boş olamaz"}
    tur = g.get("tur") if g.get("tur") in TURLER else "not"
    with KILIT, dosya_kilidi():
        d = durum_oku()
        ham = (principal.principal_id if principal is not None
               else str(g.get("kimden") or "kullanici").strip() or "kullanici")
        if principal is None and ham.casefold().strip().lstrip("@") in {
                "operator", "operatör", "operatörüm", "operatorum"}:
            return 403, {"ok": False, "hata": "operatör kaynağı doğrulanamadı"}
        source_class = "unknown"
        source_class_trust = "unverified"
        if (principal is not None
                and getattr(principal, "scope", None) == "POST /api/yaz"
                and authorization in {"operator", "agent"}):
            source_class = authorization
            source_class_trust = "verified"
        kullanici_iddiasi = ham.lower() in (
            "kullanici", "kullanıcı", "sen", "user", "human")
        # Preserve the legacy string field, but never encode an unauthenticated
        # human claim as the authoritative `kullanici` actor used by readers.
        if kullanici_iddiasi:
            kimden, ad = "unknown", "Doğrulanmamış kaynak"
        else:
            kimden, ad = ham, f"İddia: {ham.lstrip('@')}"
        kime = str(g.get("kime") or "@hepsi").strip()
        if kime and not kime.startswith("#"):
            hedef = kime.lstrip("@")
            kk = coz(d, hedef)
            kime = "@" + (adi(kk, d["kullanicilar"][kk]) if kk else hedef)
        # `kimden` gövdesi yalnızca gösterim iddiasıdır; actor_id üretmez ve
        # presence, rol, görev, workflow veya dispatch yetkisi vermez.
        m = mesaj_ekle(kimden, metin, kime=kime, tur=tur, ad=ad,
                       kaynak="panel_api", kimlik_iddiasi=ham,
                       principal=principal, source_class=source_class,
                       source_class_trust=source_class_trust)
    return 200, {"ok": True, "mesaj": m}


def api_ekran(g, principal=None):
    if type(g) is not dict:
        return 400, {"ok": False, "hata": "ekran kaydı biçimi geçersiz"}
    raw_identity = g.get("kimlik", "")
    raw_line = g.get("satir", "")
    raw_kind = g.get("tur", "ekran")
    if (type(raw_identity) is not str or type(raw_line) is not str
            or type(raw_kind) is not str):
        return 400, {"ok": False, "hata": "ekran kaydı biçimi geçersiz"}
    kimlik = principal.principal_id if principal is not None else raw_identity.strip()
    satir = raw_line.rstrip()
    if not kimlik:
        return 400, {"ok": False, "hata": "kimlik gerekli"}
    if not satir:
        return 400, {"ok": False, "hata": "satir boş olamaz"}
    if raw_kind not in EKRAN_TURLERI:
        return 400, {"ok": False, "hata": "ekran kayıt türü geçersiz"}
    tur = raw_kind
    with KILIT, dosya_kilidi():
        d = durum_oku()
        k = coz(d, kimlik)
        ad = adi(k, d["kullanicilar"][k]) if k else kimlik
        try:
            kayit = ekran_yaz(k or kimlik, ad, satir, tur, principal=principal)
        except _EKRAN_REDAKSIYON.ScreenRedactionError:
            return 400, {"ok": False,
                         "hata": "ekran kaydı güvenli biçimde işlenemedi"}
    return 200, {"ok": True, "ts": kayit["ts"],
                 "kimlik": kayit["kimlik"], "ad": kayit["ad"]}


def api_not(g, principal=None):
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


def gorev_calistir(g, principal=None, authorization=None):
    """Run task writes under the single-user local MVP or verified HMAC mode."""
    islem = str(g.get("islem") or "").strip()
    if islem not in ("ekle", "ata", "al", "sonraki", "teslim", "ilk-kontrol", "denetle", "iptal"):
        return 400, {"ok": False, "hata": f"geçersiz işlem: {islem}"}
    beklenen_policy = {
        "ekle": "task_admin", "ata": "task_admin", "iptal": "task_admin",
        "al": "task_worker", "sonraki": "task_worker",
        "teslim": "task_worker",
        "ilk-kontrol": "task_reviewer", "denetle": "task_reviewer",
    }[islem]
    if principal is not None and (
            not isinstance(getattr(principal, "principal_id", None), str)
            or not principal.principal_id
            or getattr(principal, "scope", None) != "POST /api/gorev"):
        return 403, {"ok": False,
                     "hata": "geçerli POST /api/gorev principal gerekli"}
    if principal is not None and authorization != beklenen_policy:
        return 403, {"ok": False,
                     "hata": f"görev işlemi için {beklenen_policy} policy gerekli"}
    auth_etkin = os.environ.get("YUVA_AUTH_ENABLED")
    if auth_etkin not in (None, "0", "1"):
        return 503, {"ok": False, "hata": "YUVA_AUTH_ENABLED 0 veya 1 olmalı"}
    if principal is None and auth_etkin == "1":
        return 401, {"ok": False,
                     "hata": "auth açıkken doğrulanmış task principal gerekli"}
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
    if islem == "ekle":
        if not g.get("baslik"):
            return 400, {"ok": False, "hata": "baslik gerekli"}
        if "ust_gorev_id" in g and g["ust_gorev_id"] is not None:
            try:
                g = dict(g, ust_gorev_id=ust_gorev_id_coz(g["ust_gorev_id"]))
            except ValueError:
                return 400, {"ok": False,
                             "hata": "ust_gorev_id boşluksuz kanonik pozitif tamsayı olmalı; kök görev için null kullanın"}
    elif islem != "sonraki" and not g.get("id"):
        return 400, {"ok": False, "hata": "id gerekli"}
    actor = (principal.principal_id if principal is not None
             else g.get("kimden"))
    if not isinstance(actor, str) or not actor.strip():
        return 400, {"ok": False,
                     "hata": "yerel görev işleminde kimden aktör etiketi gerekli"}
    global _TASK_CORE
    with _TASK_CORE_LOCK:
        try:
            if _TASK_CORE is None:
                loader = SourceFileLoader("yuva_task_core", str(CLI))
                spec = importlib.util.spec_from_loader("yuva_task_core", loader)
                if spec is None or spec.loader is None:
                    raise RuntimeError(f"CLI yüklenemedi: {CLI}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                _TASK_CORE = module
            core = _TASK_CORE
        except Exception as e:
            event_id = _guvenli_hata_kaydi("task_core_load", e)
            return 500, {"ok": False,
                         "hata": "Görev işlemi başlatılamadı; yönetici tanı kaydını kontrol edebilir.",
                         "olay_id": event_id}
    output = io.StringIO()
    diagnostic_output = io.StringIO()
    try:
        # redirect_stdout is process-global; serialize only this small mutation
        # bridge so concurrent requests cannot mix captured responses.
        with _TASK_CORE_LOCK, contextlib.redirect_stdout(output), \
                contextlib.redirect_stderr(diagnostic_output):
            core.run_task_operation(islem, g, actor, principal)
    except SystemExit:
        return 400, {"ok": False,
                     "hata": "Görev isteği reddedildi; gerekli alanları ve görev durumunu kontrol edin."}
    except PermissionError:
        return 403, {"ok": False, "hata": "Bu görev işlemi için gerekli yetki yok."}
    except Exception as e:
        event_id = _guvenli_hata_kaydi("task_operation", e)
        return 500, {"ok": False,
                     "hata": "Görev işlemi tamamlanamadı; yönetici tanı kaydını kontrol edebilir.",
                     "olay_id": event_id}
    cikti = output.getvalue().strip()
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


def auth_gate_yukle():
    """Build the optional HMAC gate from explicit operator configuration.

    The absent/"0" flag keeps legacy behavior without importing auth modules.
    Enabled mode requires a pre-provisioned store and never falls back to an
    anonymous gate if config, import, or store validation fails.
    """
    etkin = os.environ.get("YUVA_AUTH_ENABLED")
    if etkin is None or etkin == "0":
        return None
    if etkin != "1":
        raise ValueError("YUVA_AUTH_ENABLED must be exactly 0 or 1")

    kok = os.environ.get("YUVA_AUTH_STORE_ROOT")
    audience = os.environ.get("YUVA_AUTH_AUDIENCE")
    if not kok or not audience:
        raise ValueError("YUVA_AUTH_STORE_ROOT and YUVA_AUTH_AUDIENCE are required")

    raw_admins = os.environ.get("YUVA_AUTH_ADMIN_PRINCIPALS", "")
    admins = raw_admins.split(",") if raw_admins else []
    for principal_id in admins:
        valid_chars = (principal_id.isascii()
                       and all(c.isalnum() or c in "._:@-" for c in principal_id))
        if (not principal_id or principal_id != principal_id.strip()
                or len(principal_id) > 128 or not principal_id[0].isalnum()
                or not valid_chars):
            raise ValueError("YUVA_AUTH_ADMIN_PRINCIPALS contains an invalid ID")
    if len(set(admins)) != len(admins):
        raise ValueError("YUVA_AUTH_ADMIN_PRINCIPALS contains duplicates")

    if __package__:
        from .auth import HMACAuthenticator
        from .auth_integration_draft import AuthGate
        from .auth_store_v2 import AuthStateStore
    else:
        from auth import HMACAuthenticator
        from auth_integration_draft import AuthGate
        from auth_store_v2 import AuthStateStore

    store = AuthStateStore(kok)
    state = store.read()  # validates the pre-provisioned root, lock, and snapshot
    if state["audience"] != audience:
        raise ValueError("configured audience does not match auth store")
    verifier = HMACAuthenticator(store=store, audience=audience)
    return AuthGate(verifier, admin_principals=frozenset(admins))


def auth_hata_yaniti(e):
    """Return a bounded safe response for an auth failure."""
    status = getattr(e, "status", None)
    code = getattr(e, "code", None)
    if (type(status) is not int or status not in (400, 401, 403, 404, 503)
            or not isinstance(code, str) or not code or len(code) > 64
            or not all(c.isascii() and (c.islower() or c.isdigit() or c == "_")
                       for c in code)):
        return 503, {"ok": False, "hata": "authentication_unavailable"}
    return status, {"ok": False, "hata": code}


# ── anlık görüntü ────────────────────────────────────────────────────

class PanelSnapshot(dict):
    """Snapshot dict with private, non-serialized screen cursor commit data."""

    def __init__(self, *args, screen_cursor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.screen_cursor = screen_cursor


def veri(defer_screen_cursor=False):
    """Tek kilitli kritik bölgede tutarlı anlık görüntü (durum + görev aynı rev'den).

    Salt okunur; CLI subprocess çağrılmaz, bu yüzden kilit burada güvenle tutulur.
    """
    with KILIT, dosya_kilidi():
        d = durum_oku(snapshot=True)
        g = gorev_oku(snapshot=True)
        ks = {}
        for k, v in d["kullanicilar"].items():
            ks[k] = {
                "kimlik": k,
                "ad": adi(k, v),
                "arac": v.get("arac", "diger"),
                "rol": v.get("rol", "isci"),
                "bas_denetci": bool(v.get("bas_denetci")),
                "sorumlu_kimlik": v.get("sorumlu_kimlik"),
                "son_okuma": v.get("son_okuma"),
                # G1/W1b yokken hiçbir persisted heartbeat/presence alanı
                # doğrulanmış aktör kanıtı değildir; UI yeşil gösteremez.
                "online": False,
                "presence_state": "unknown",
                "presence_verified": False,
            }
        # CLI presence freshness contract: always expose the integer TTL.
        ekranlar, ekranlar_meta = tum_ekranlar(
            defer_cursor_commit=defer_screen_cursor)
        cursor = None
        if defer_screen_cursor:
            cursor = (ekranlar_meta.pop("_cursor_before", None),
                      ekranlar_meta.pop("_last_considered", None))
        snapshot = {"ok": True, "simdi": simdi(), "online_sn": int(ONLINE_SN),
                    "rev": d.get("rev", 0), "kullanicilar": ks,
                    "gorevler": [_gorev_snapshot_proje(task)
                                 for task in g.get("gorevler", [])],
                    "mesajlar": mesajlar(),
                    "ekranlar": ekranlar, "ekranlar_meta": ekranlar_meta}
        if defer_screen_cursor:
            return PanelSnapshot(snapshot, screen_cursor=cursor)
        return snapshot


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
    AUTH_GATE = None
    # No browser-session issuer is provisioned in this release. Protected GETs
    # stay unavailable until an explicit server-side verifier is installed.
    BROWSER_SESSION_GATE = None

    def end_headers(self):
        """Apply the common browser/cache policy to every HTTP response path."""
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def send_error(self, code, message=None, explain=None):
        """Keep stdlib-generated protocol errors from reflecting request data."""
        safe_message = self.responses.get(code, ("HTTP error", ""))[0]
        return super().send_error(
            code, safe_message, "The request could not be processed.")

    # ── kaynak (Host/Origin/Content-Type) denetimi ───────────────────────
    # Host/Origin denetimi kimlik doğrulaması değildir. Opsiyonel HMAC kapısı
    # yalnız açıkça yapılandırıldığında mutasyon POST'larını doğrular; GET ve
    # doğrudan aynı-UID dosya erişimi bu kapının kapsamı dışındadır. Loopback
    # dışı bind ve istemci bu görevde her durumda reddedilir.
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
        """Origin yalnız geçerli bir HTTP origin'i olarak Host ile eşleşirse geçer.

        Kural: şema http olmalı (panel http ile sunulur; https kabul edilmez),
        ad loopback listesinde olmalı ve host+port doğrulanmış Host authority ile
        aynı olmalı. Böylece 'Host: localhost:8686' + 'Origin: http://başka:8686'
        gibi uyumsuz (ve rebinding şüpheli) birleşimler reddedilir.
        """
        try:
            p = urlsplit(ham)
            if (p.scheme != "http" or not p.hostname or p.username is not None
                    or p.password is not None or p.path or p.query or p.fragment):
                return False
            oh = p.hostname.lower()
            if oh not in self.IZINLI_HOSTLAR:
                return False
            beklenen_port = int(host_port)
            origin_port = p.port  # malformed ports raise ValueError
        except (TypeError, ValueError):
            return False
        host_yetkisi = f"[{oh}]" if ":" in oh else oh
        if origin_port is None:
            # An omitted port is valid only for HTTP's default port, with no
            # empty/trailing colon. The panel Host header itself always has a port.
            if beklenen_port != 80 or p.netloc.lower() != host_yetkisi:
                return False
        elif (origin_port != beklenen_port
              or p.netloc.lower() != f"{host_yetkisi}:{origin_port}"):
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
            return 403, {"ok": False, "hata": "Yalnızca loopback istemcilerine izin verilir."}
        host_basliklari = self.headers.get_all("Host", [])
        if len(host_basliklari) != 1:
            return 403, {"ok": False, "hata": "Tek bir Host başlığı gerekli."}
        ham_host = host_basliklari[0]
        if not ham_host or not str(ham_host).strip():
            return 403, {"ok": False, "hata": "Host başlığı gerekli"}
        ad, port = self._host_ayristir(ham_host)
        if ad not in self.IZINLI_HOSTLAR:
            return 403, {"ok": False,
                         "hata": "İzin verilmeyen Host başlığı; loopback adresi ve doğru portu kullanın."}
        if not port:
            # Standart dışı port kullanıldığı için portsuz Host kabul edilmez.
            return 403, {"ok": False,
                         "hata": "Host başlığı panelin yapılandırılmış portunu içermeli."}
        if self.SUNUCU_PORT is not None and port != str(self.SUNUCU_PORT):
            return 403, {"ok": False,
                         "hata": "İzin verilmeyen Host portu; panelin yapılandırılmış portunu kullanın."}
        origin_basliklari = self.headers.get_all("Origin", [])
        if len(origin_basliklari) > 1:
            return 403, {"ok": False, "hata": "Birden fazla Origin başlığı reddedildi."}
        ham_origin = origin_basliklari[0] if origin_basliklari else None
        if ham_origin is not None:
            o = str(ham_origin).strip()
            if not o or o.lower() == "null" or not self._origin_gecerli(o, ad, port):
                return 403, {"ok": False, "hata": "İzin verilmeyen Origin başlığı."}
        if post:
            ct_basliklari = self.headers.get_all("Content-Type", [])
            if len(ct_basliklari) != 1:
                return 415, {"ok": False,
                             "hata": "Tek bir Content-Type: application/json başlığı gerekli."}
            ct = ct_basliklari[0].split(";")[0].strip().lower()
            if ct != "application/json":
                return 415, {"ok": False,
                             "hata": "POST için Content-Type application/json olmalı."}
        return None

    def _gonder(self, kod, govde, tur="application/json; charset=utf-8", kapat=False):
        if isinstance(govde, (dict, list)):
            govde = json.dumps(govde, ensure_ascii=False)
        b = govde.encode("utf-8") if isinstance(govde, str) else govde
        self.send_response(kod)
        self.send_header("Content-Type", tur)
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

    def _snapshot_gonder(self, snapshot):
        """Send an opted-in GET snapshot through the global byte selector."""
        try:
            selector = _snapshot_budget_modulu_yukle()
            screen_order = list(snapshot["ekranlar"])
            result = selector.build_response(snapshot, screen_order=screen_order)
        except Exception:
            try:
                result = _snapshot_budget_modulu_yukle().error_response(
                    "snapshot_response_unavailable")
            except Exception:
                return self._gonder(503, {
                    "ok": False, "hata": "snapshot_response_unavailable"})

        if result.status == 200:
            cursor = getattr(snapshot, "screen_cursor", None)
            if isinstance(cursor, tuple) and len(cursor) == 2:
                _ekran_secim_ilerlet(*cursor)
        return self._gonder(result.status, result.body)

    def _browser_get_authorize(self, route, scope):
        """Require an explicit server-side session verifier before GET dispatch.

        The verifier contract is ``authorize_get(route, scope, cookie)`` and
        must return the literal boolean True. HMAC POST auth and identity headers
        are intentionally not consulted here.
        """
        gate = self.BROWSER_SESSION_GATE
        if gate is None:
            return 503, {"ok": False, "hata": "browser_session_unavailable"}
        cookie_headers = self.headers.get_all("Cookie", [])
        if len(cookie_headers) > 1:
            return 401, {"ok": False, "hata": "browser_session_required"}
        cookie = cookie_headers[0] if cookie_headers else None
        try:
            accepted = gate.authorize_get(route, scope, cookie)
        except PermissionError:
            return 403, {"ok": False, "hata": "browser_scope_denied"}
        except Exception:
            return 503, {"ok": False, "hata": "browser_session_unavailable"}
        if accepted is not True:
            return 401, {"ok": False, "hata": "browser_session_required"}
        return None

    def _durum_hatasi(self, e):
        """Expose actionable guidance and a bounded correlation ID, never raw data."""
        event_id = _guvenli_hata_kaydi("persistent_state", e)
        return self._gonder(500, {
            "ok": False,
            "hata": ("Yuva verisi okunamadı veya yazılamadı; dosya otomatik "
                     "değiştirilmedi. İzin/disk durumunu kontrol edin; bozuk JSON "
                     "için elle onarım veya güvenilir yedekten dönüş gerekir."),
            "olay_id": event_id,
        })

    def _govde_oku(self):
        """POST gövdesini sınırlı ve fail-closed okur.

        Dönüş: (govde_baytlari, hata) — hata (kod, govde) demetidir.
        JSON çözümünden ve uç çağrısından ÖNCE çalışır. Yinelenen uzunluk
        başlıkları body okunmadan reddedilir; do_POST bağlantıyı kapatır ki
        çerçevesi belirsiz kalan baytlar sonraki istek gibi işlenmesin.
        """
        if self.headers.get("Transfer-Encoding"):
            return None, (400, {"ok": False,
                                "hata": "Transfer-Encoding desteklenmiyor; Content-Length kullanın"})
        uzunluklar = self.headers.get_all("Content-Length", [])
        if len(uzunluklar) > 1:
            return None, (400, {"ok": False,
                                "hata": "birden fazla Content-Length desteklenmiyor"})
        if not uzunluklar:
            return b"", None          # gövdesiz istek: mevcut istemci sözleşmesi korunur
        ham_cl = uzunluklar[0]
        cl = str(ham_cl).strip()
        if not cl or not cl.isascii() or not cl.isdecimal():
            return None, (400, {"ok": False, "hata": "Content-Length geçersiz."})
        n = int(cl)
        if n > GOVDE_SINIR:
            return None, (413, {"ok": False,
                                "hata": f"gövde çok büyük: {n} bayt > {GOVDE_SINIR} bayt sınır"})
        if n == 0:
            return b"", None
        try:
            ham = self.rfile.read(n)
        except Exception:
            return None, (400, {"ok": False, "hata": "İstek gövdesi okunamadı."})
        if len(ham) != n:
            return None, (400, {"ok": False,
                                "hata": f"eksik gövde: {len(ham)}/{n} bayt alındı"})
        return ham, None

    def do_GET(self):
        request_parts = self.requestline.split()
        if len(request_parts) != 3:
            return self._gonder(400, {"ok": False,
                                     "hata": "invalid request target"})
        raw_target = request_parts[1]
        route, malformed_alias = browser_get_route(raw_target)
        if malformed_alias:
            return self._gonder(400, {"ok": False,
                                     "hata": "canonical browser route required"})
        if route is None:
            return self._gonder(404, {"ok": False,
                                     "hata": "İstenen yol bulunamadı."})
        hata = self._kaynak_denetimi()
        if hata:
            return self._gonder(hata[0], hata[1])
        scope = BROWSER_GET_ROUTE_POLICY[route]
        access_error = self._browser_get_authorize(route, scope)
        if access_error is not None:
            return self._gonder(access_error[0], access_error[1])
        if scope == "snapshot.read":
            try:
                budget_flag = os.environ.get(SNAPSHOT_BUDGET_ENV, "0")
                if budget_flag not in ("0", "1"):
                    return self._gonder(503, {
                        "ok": False,
                        "hata": "snapshot_budget_configuration_invalid"})
                if budget_flag == "1":
                    return self._snapshot_gonder(veri(defer_screen_cursor=True))
                return self._gonder(200, veri())
            except SnapshotSourceLimit as e:
                return self._gonder(503, {
                    "ok": False,
                    "hata": "snapshot_source_limit",
                    "kaynak": e.source,
                    "limit_bayt": e.limit_bytes,
                })
            except DurumHatasi as e:
                return self._durum_hatasi(e)
        if scope == "browser.shell":
            return self._gonder(200, sayfa(), "text/html; charset=utf-8")
        return self._gonder(404, {"ok": False, "hata": "İstenen yol bulunamadı."})

    def do_OPTIONS(self):
        """CORS ön-uçuşuna izin verilmez: Access-Control-Allow-* üretilmez."""
        self.close_connection = True
        self.send_response(405)
        self.send_header("Allow", "GET, POST")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_POST(self):
        hata = self._kaynak_denetimi(post=True)
        if hata:
            # Gövde okunmadı: kalan baytlar sonraki isteğin çerçevesini bozmasın.
            return self._gonder(hata[0], hata[1], kapat=True)
        ham, hata = self._govde_oku()
        if hata:
            kod, govde = hata
            return self._gonder(kod, govde, kapat=True)

        authn = None
        if self.AUTH_GATE is not None:
            try:
                # Authenticate the untouched request-target and raw bytes before
                # parsing JSON or looking up a handler.
                authn = self.AUTH_GATE.authenticate_post(self.path, self.headers, ham)
                if authn is None:
                    raise RuntimeError("enabled auth gate returned no principal")
            except Exception as e:
                kod, govde = auth_hata_yaniti(e)
                return self._gonder(kod, govde, kapat=True)

        try:
            g = json.loads(ham.decode("utf-8")) if ham else {}
            if not isinstance(g, dict):
                raise ValueError
        except (UnicodeError, ValueError, TypeError):
            return self._gonder(400, {"ok": False,
                                      "hata": "İstek gövdesi geçerli bir JSON nesnesi olmalı."})

        authorization = None
        if self.AUTH_GATE is not None:
            try:
                authorization = self.AUTH_GATE.authorize_payload(authn, g)
            except Exception as e:
                kod, govde = auth_hata_yaniti(e)
                return self._gonder(kod, govde, kapat=True)

        yol = (authn.route if authn is not None
               else (self.path.split("?")[0] or "/").rstrip("/"))
        fn = UCLAR.get(yol)
        if not fn:
            return self._gonder(404, {"ok": False, "hata": "İstenen uç bulunamadı."})
        try:
            if authn is None:
                kod, cevap = fn(g)
            elif yol == "/api/gorev":
                kod, cevap = fn(g, principal=authn.principal,
                                authorization=authorization)
            elif yol == "/api/yaz":
                kod, cevap = fn(g, principal=authn.principal,
                                authorization=authorization)
            else:
                kod, cevap = fn(g, principal=authn.principal)
        except DurumHatasi as e:
            return self._durum_hatasi(e)
        except Exception as e:
            event_id = _guvenli_hata_kaydi("request_handler", e)
            return self._gonder(500, {
                "ok": False,
                "hata": "İstek işlenemedi; yönetici tanı kaydını kontrol edebilir.",
                "olay_id": event_id,
            })
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
    os.umask(0o077)
    try:
        kok_fd = guvenli_dizin_fd(KOK, olustur=True)
        try:
            ekran_fd = guvenli_alt_dizin_fd(kok_fd, EKRAN.name, olustur=True)
            os.close(ekran_fd)
        finally:
            os.close(kok_fd)
    except (OSError, DurumHatasi):
        sys.exit("❌ JSONL veri dizini güvenli değil; izin/disk durumunu kontrol edin. "
                 "Otomatik izin düzeltmesi yapılmadı.")
    # Kaynak denetimi gerçek dinleme portuna bağlanır. Loopback dışı bind her
    # durumda fail-closed reddedilir; optional HMAC gate loopback'i genişletmez.
    if not loopback_mi(a.host):
        sys.exit(f"❌ --host {a.host!r} loopback dışı: bu sunucuda kimlik doğrulama YOK, "
                 "uzaktan erişim desteklenmez (yalnız localhost/127.0.0.1/::1).")
    H.SUNUCU_PORT = a.port
    H.IZINLI_HOSTLAR.add((a.host or "").strip().strip("[]").lower())
    try:
        H.AUTH_GATE = auth_gate_yukle()
    except Exception as e:
        neden = getattr(e, "code", type(e).__name__)
        sys.exit(f"❌ HMAC auth yapılandırması geçersiz; panel başlatılmadı ({neden})")
    print(f"🪹 panel dinliyor: http://localhost:{a.port}")
    try:
        sunucu = Sunucu((a.host, a.port), H)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            sys.exit(f"❌ {a.host}:{a.port} zaten kullanımda. Hiçbir süreç durdurulmadı; "
                     "sahipliği doğrulamak için 'yuva panel status', yalnız doğrulanmış "
                     "Yuva servisini yönetmek için 'yuva panel stop' kullanın.")
        raise
    try:
        sunucu.serve_forever()
    finally:
        sunucu.server_close()
