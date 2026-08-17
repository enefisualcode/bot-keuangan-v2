"""
BOT PENCATAT KEUANGAN - TELEGRAM (MULTI-USER)
==============================================
Setiap user pakai Google Spreadsheet MILIK SENDIRI.
Mapping user -> spreadsheet disimpan di sheet "Users" pada spreadsheet master
(milik pemilik bot).

Perintah:
  /start           -> panduan
  /daftar <id>     -> hubungkan spreadsheet milik user
  /info            -> lihat spreadsheet yang terhubung
  /catat <nominal> <kategori> <catatan>
  /masuk  <nominal> <catatan>
  kirim foto struk -> dibaca AI

Sheet yang dibuat otomatis di spreadsheet user:
  Pengeluaran : Tanggal | Kategori | Nominal | Merchant | Sumber | Catatan | Tipe Bayar
  Pemasukan   : Tanggal | Kategori | Nominal | Sumber   | Catatan
"""

import logging
import json
import re
import os
import uuid
import asyncio
from datetime import datetime, timedelta, timezone

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import google.generativeai as genai
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==========================================
# KONFIGURASI
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Spreadsheet MASTER milik pemilik bot -> tempat menyimpan daftar user
MASTER_SPREADSHEET_ID = os.environ.get("MASTER_SPREADSHEET_ID", "")
USERS_SHEET = os.environ.get("USERS_SHEET", "Users")

# Telegram ID pemilik bot (untuk /umumkan). Cek ID-mu lewat /myid.
ADMIN_ID = os.environ.get("ADMIN_ID", "").strip()

# Nama sheet di spreadsheet masing-masing user
SHEET_PENGELUARAN = os.environ.get("SHEET_PENGELUARAN", "Pengeluaran")
SHEET_PEMASUKAN = os.environ.get("SHEET_PEMASUKAN", "Pemasukan")
SHEET_DASHBOARD = os.environ.get("SHEET_DASHBOARD", "Dashboard")

CREDENTIALS_FILE = "credentials.json"
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")

if GOOGLE_CREDENTIALS_JSON:
    with open(CREDENTIALS_FILE, "w") as f:
        f.write(GOOGLE_CREDENTIALS_JSON)

# Email service account, dipakai untuk instruksi share ke user
try:
    with open(CREDENTIALS_FILE) as f:
        SERVICE_ACCOUNT_EMAIL = json.load(f).get("client_email", "(cek credentials.json)")
except Exception:
    SERVICE_ACCOUNT_EMAIL = "(cek credentials.json)"

HEADER_PENGELUARAN = ["Tanggal", "Kategori", "Nominal", "Merchant",
                      "Sumber", "Catatan", "Tipe Bayar", "Barang"]
HEADER_PEMASUKAN = ["Tanggal", "Kategori", "Nominal", "Sumber", "Catatan"]
HEADER_USERS = ["user_id", "username", "spreadsheet_id", "tanggal_daftar"]

# ==========================================
# WAKTU: selalu pakai WIB (server Railway pakai UTC)
# ==========================================
WIB = timezone(timedelta(hours=7))


def now_wib():
    return datetime.now(WIB)

# ==========================================
# KATEGORI BAKU + normalisasi
# ==========================================
KATEGORI_BAKU = ["Makan", "Donasi", "Transport", "Belanja",
                 "Hiburan", "Tagihan", "Investasi", "Lainnya"]

# Kata kunci -> kategori. Dicocokkan ke gabungan (kategori + merchant), huruf kecil.
# Urutan penting: yang lebih spesifik didahulukan; "Makan" paling umum, ditaruh akhir.
PETA_KATEGORI = {
    "Investasi": ["investasi", "invest", "indodax", "kripto", "crypto", "bitcoin",
                  "btc", "reksadana", "saham", "bibit", "ajaib", "pluang", "pintu",
                  "emas", "antam", "deposito", "kki-depo"],
    "Tagihan": ["tagihan", "pln", "listrik", "pulsa", "paket data", "indihome",
                "wifi", "apple", "icloud", "google", "langganan", "subscription",
                "cicilan", "pay later", "paylater", "kredivo", "akulaku",
                "spaylater", "bpjs", "asuransi", "netflix", "spotify"],
    "Hiburan": ["hiburan", "warnet", "game", "gaming", "spade", "arafah", "aratan",
                "playstation", "bioskop", "cinema", "xxi", "cgv", "steam",
                "billiard", "biliar", "karaoke", "goc"],
    "Transport": ["transport", "bensin", "pertamina", "shell", "vivo", "parkir",
                  "parkiran", "ojek", "gojek", "grab", "gocar", "goride", "maxim",
                  "krl", "mrt", "busway", "transjakarta", "tol", "e-toll", "spbu",
                  "bbm", "solar", "pertalite", "pertamax"],
    "Belanja": ["belanja", "alfamart", "alfamidi", "indomaret", "tokopedia",
                "shopee", "lazada", "tokped", "skintific", "pinzy", "jastip",
                "store", "mart", "market", "supermarket", "hypermart", "watsons",
                "guardian", "pinzy"],
    "Donasi": ["donasi", "sedekah", "shodaqoh", "zakat", "infaq", "infak",
               "wakaf", "sumbangan", "amal", "kurban", "qurban", "kitabisa",
               "dompet dhuafa", "rumah zakat", "baznas", "yatim", "charity"],
    "Makan": ["makan", "warteg", "nasi", "ayam", "bakso", "mie", "sushi",
              "gorengan", "cimol", "gado", "kebab", "roti", "kantin", "warung",
              "resto", "food", "seblak", "telor", "telur", "jajan", "snack",
              "martabak", "sate", "soto", "padang", "geprek", "burger", "pizza",
              "kfc", "mcd", "richeese", "dimsum", "hachi", "kabobs", "goreng",
              "kopi", "coffee", "fore", "kenangan", "starbucks", "janji jiwa",
              "point coffee", "tuku", "juice", "jus", "boba", "milk tea",
              "es teh", "ngopi"],
}


def normalkan_kategori(teks, merchant="", paksa=False):
    """Petakan kategori bebas ke salah satu KATEGORI_BAKU.
    - Kalau sudah kategori baku (selain Lainnya), dihormati.
    - Kalau Lainnya/tak jelas, coba diselamatkan lewat kata kunci + nama merchant.
    - paksa=True (untuk struk): kalau tetap tak cocok -> Lainnya.
    - paksa=False (manual): kalau tak cocok -> hormati yang diketik user."""
    t = (teks or "").strip()
    for k in KATEGORI_BAKU:
        if t.lower() == k.lower():
            if k != "Lainnya":
                return k
            break
    kandidat = f"{t} {merchant}".lower()
    for kategori, kata in PETA_KATEGORI.items():
        if any(kk in kandidat for kk in kata):
            return kategori
    if paksa:
        return "Lainnya"
    return t.title() if t else "Lainnya"

# ==========================================
# LOGGING
# ==========================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ==========================================
# GEMINI
# ==========================================
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.5-flash")

# ==========================================
# GOOGLE SHEETS
# ==========================================
_client = None


def get_client():
    """Satu koneksi gspread dipakai berulang, supaya tidak auth tiap request."""
    global _client
    if _client is None:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        _client = gspread.authorize(creds)
    return _client


def get_or_create_worksheet(spreadsheet, nama, header):
    """Ambil worksheet; kalau belum ada, buat sekalian dengan headernya."""
    try:
        return spreadsheet.worksheet(nama)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=nama, rows=1000, cols=len(header) + 3)
        ws.append_row(header, value_input_option="USER_ENTERED")
        return ws



# ------------------------------------------
# Dashboard otomatis di spreadsheet user
# ------------------------------------------
# CATATAN PENTING SOAL FORMULA
# Google Sheets memakai pemisah argumen yang berbeda tergantung lokal:
#   en_US        -> koma      : SUM(A1, B1)   array: {A1, B1}
#   id_ID / dll  -> titik koma: SUM(A1; B1)   array: {A1 \\ B1}
# Semua template di bawah memakai penanda netral:
#   ~  = pemisah argumen
#   ^  = pemisah kolom pada array literal
# Koma di dalam string QUERY ("select A, sum(C)") sengaja dibiarkan apa adanya
# karena itu bagian dari bahasa QUERY, bukan pemisah argumen formula.

T_KEY_PERIODE = '=TEXT(EDATE(TODAY()~IF(DAY(TODAY())>=25~0~-1))~"YYYY-MM")'

T_LABEL_PERIODE = (
    '=IF(DAY(TODAY())>=25~'
    'TEXT(DATE(YEAR(TODAY())~MONTH(TODAY())~25)~"d mmm")&" - "&'
    'TEXT(DATE(YEAR(TODAY())~MONTH(TODAY())+1~24)~"d mmm yyyy")~'
    'TEXT(DATE(YEAR(TODAY())~MONTH(TODAY())-1~25)~"d mmm")&" - "&'
    'TEXT(DATE(YEAR(TODAY())~MONTH(TODAY())~24)~"d mmm yyyy"))'
)


def _t_helper(sheet):
    """Label periode 25-24 untuk tiap baris transaksi."""
    return (
        '=ARRAYFORMULA(IF({s}!A2:A5000=""~""~'
        'TEXT(EDATE({s}!A2:A5000~IF(DAY({s}!A2:A5000)>=25~0~-1))~"YYYY-MM")))'
    ).format(s=sheet)


def deteksi_pemisah(ss):
    """Tentukan pemisah argumen dari lokal spreadsheet.
    Lokal yang memakai koma sebagai desimal (id_ID, de_DE, ...) memakai ';'."""
    try:
        locale = (ss.fetch_sheet_metadata()
                  .get("properties", {}).get("locale", "en_US"))
    except Exception:
        locale = "en_US"
    if locale.startswith(("en", "ms", "ja", "ko", "zh", "th", "he", "iw")):
        return ",", ","
    return ";", "\\"


def _isi_dashboard(ws, sep, colsep):
    """Tulis semua formula ke sheet Dashboard memakai pemisah yang sesuai."""

    def f(t):
        return t.replace("~", sep).replace("^", colsep)

    P, M = SHEET_PENGELUARAN, SHEET_PEMASUKAN

    ws.batch_update([
        # --- Blok ringkasan (A:B) ---
        {"range": "A1", "values": [["  RINGKASAN PERIODE BERJALAN"]]},
        {"range": "A2:A6", "values": [
            ["Periode"], ["Total Pemasukan"], ["Total Pengeluaran"],
            ["Selisih"], ["Rata-rata Harian"],
        ]},
        {"range": "B2", "values": [[f(T_LABEL_PERIODE)]]},
        {"range": "B3", "values": [[f(
            '=SUMIF($M$2:$M$5000~$K$1~' + M + '!$C$2:$C$5000)')]]},
        {"range": "B4", "values": [[f(
            '=SUMIF($L$2:$L$5000~$K$1~' + P + '!$C$2:$C$5000)')]]},
        {"range": "B5", "values": [["=B3-B4"]]},
        {"range": "B6", "values": [[f(
            '=IFERROR(B4/COUNTA(UNIQUE(FILTER(' + P + '!$A$2:$A$5000~'
            '$L$2:$L$5000=$K$1)))~0)')]]},

        # --- Blok pengeluaran per kategori (A8:B) ---
        {"range": "A8", "values": [["  PENGELUARAN PER KATEGORI"]]},
        {"range": "A9:B9", "values": [["Kategori", "Total"]]},
        {"range": "A10", "values": [[f(
            '=IFERROR(SORT(UNIQUE(FILTER($N$2:$N$5000~'
            '$N$2:$N$5000<>""))~1~TRUE)~"")')]]},
        {"range": "B10", "values": [[f(
            '=ARRAYFORMULA(IF($A$10:$A$40=""~""~'
            'SUMIF($N$2:$N$5000~$A$10:$A$40~'
            + P + '!$C$2:$C$5000)))')]]},

        # --- Blok rekap harian (D:E) ---
        {"range": "D1", "values": [["  REKAP HARIAN"]]},
        {"range": "D2", "values": [[f(
            '=IFERROR(QUERY(' + P + '!A2:C5000~'
            '"select A, sum(C) where A is not null '
            'group by A order by A desc '
            "label A 'Tanggal', sum(C) 'Total'\"~0)~\"\")"
        )]]},

        # --- Blok riwayat per periode (G:I) ---
        {"range": "G1", "values": [["  RIWAYAT PER PERIODE"]]},
        {"range": "G2:I2", "values": [["Periode", "Pengeluaran", "Pemasukan"]]},
        {"range": "G3", "values": [[f(
            '=IFERROR(SORT(UNIQUE(FILTER($L$2:$L$5000~'
            '$L$2:$L$5000<>""))~1~FALSE)~"")')]]},
        {"range": "H3", "values": [[f(
            '=ARRAYFORMULA(IF($G$3:$G$300=""~""~'
            'SUMIF($L$2:$L$5000~$G$3:$G$300~' + P + '!$C$2:$C$5000)))')]]},
        {"range": "I3", "values": [[f(
            '=ARRAYFORMULA(IF($G$3:$G$300=""~""~'
            'SUMIF($M$2:$M$5000~$G$3:$G$300~' + M + '!$C$2:$C$5000)))')]]},

        # --- Sel bantuan (K:M), disembunyikan ---
        {"range": "K1", "values": [[f(T_KEY_PERIODE)]]},
        {"range": "L2", "values": [[f(_t_helper(P))]]},
        {"range": "M2", "values": [[f(_t_helper(M))]]},
        {"range": "N2", "values": [[f(
            '=ARRAYFORMULA(IF(($L$2:$L$5000=$K$1)*'
            '(' + P + '!$B$2:$B$5000<>"")~'
            + P + '!$B$2:$B$5000~""))')]]},
    ], value_input_option="USER_ENTERED")


def _rapikan_dashboard(ss, ws):
    sid = ws.id
    judul = {"textFormat": {"bold": True, "fontSize": 10,
                            "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
             "backgroundColor": {"red": 0.25, "green": 0.25, "blue": 0.25},
             "verticalAlignment": "MIDDLE"}
    tebal = {"textFormat": {"bold": True, "fontSize": 10},
             "backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85}}
    angka = {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}}

    def rng(r1, c1, r2, c2):
        return {"sheetId": sid, "startRowIndex": r1, "endRowIndex": r2,
                "startColumnIndex": c1, "endColumnIndex": c2}

    def repeat(r, fmt, fields):
        return {"repeatCell": {"range": r, "cell": {"userEnteredFormat": fmt},
                               "fields": fields}}

    reqs = [
        {"mergeCells": {"range": rng(0, 0, 1, 2), "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": rng(0, 3, 1, 5), "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": rng(0, 6, 1, 9), "mergeType": "MERGE_ALL"}},
        repeat(rng(0, 0, 1, 2), judul, "userEnteredFormat"),
        repeat(rng(0, 3, 1, 5), judul, "userEnteredFormat"),
        repeat(rng(0, 6, 1, 9), judul, "userEnteredFormat"),
        {"mergeCells": {"range": rng(7, 0, 8, 2), "mergeType": "MERGE_ALL"}},
        repeat(rng(7, 0, 8, 2), judul, "userEnteredFormat"),
        repeat(rng(8, 0, 9, 2), tebal, "userEnteredFormat"),
        repeat(rng(9, 1, 40, 2), angka, "userEnteredFormat.numberFormat"),
        repeat(rng(1, 3, 2, 5), tebal, "userEnteredFormat"),
        repeat(rng(1, 6, 2, 9), tebal, "userEnteredFormat"),
        repeat(rng(2, 1, 6, 2), angka, "userEnteredFormat.numberFormat"),
        repeat(rng(2, 3, 300, 4),
               {"numberFormat": {"type": "DATE",
                                 "pattern": "ddd, dd mmm yyyy"}},
               "userEnteredFormat.numberFormat"),
        repeat(rng(2, 4, 300, 5), angka, "userEnteredFormat.numberFormat"),
        repeat(rng(2, 7, 300, 9), angka, "userEnteredFormat.numberFormat"),
        repeat(rng(4, 0, 5, 2),
               {"textFormat": {"bold": True, "fontSize": 10}},
               "userEnteredFormat.textFormat"),
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": 10, "endIndex": 14},
            "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}},
        {"updateSheetProperties": {
            "properties": {"sheetId": sid, "index": 0,
                           "gridProperties": {"hideGridlines": True}},
            "fields": "index,gridProperties.hideGridlines"}},
    ]
    for c1, c2, px in [(0, 1, 165), (1, 2, 135), (2, 3, 24),
                       (3, 4, 150), (4, 5, 110), (5, 6, 24),
                       (6, 7, 100), (7, 8, 120), (8, 9, 120)]:
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": c1, "endIndex": c2},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})

    ss.batch_update({"requests": reqs})


def rapikan_header(ss, ws, jumlah_kolom, warna):
    """Percantik baris header sheet data: tebal, berwarna, dibekukan."""
    sid = ws.id
    lebar = {SHEET_PENGELUARAN: [(0, 1, 110), (1, 2, 120), (2, 3, 110),
                                 (3, 4, 200), (4, 5, 85), (5, 6, 190),
                                 (6, 7, 100)],
             SHEET_PEMASUKAN: [(0, 1, 110), (1, 2, 165), (2, 3, 120),
                               (3, 4, 85), (4, 5, 200)]}
    reqs = [
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": jumlah_kolom},
            "cell": {"userEnteredFormat": {
                "backgroundColor": warna,
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "textFormat": {"bold": True, "fontSize": 10,
                               "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}},
            "fields": "userEnteredFormat"}},
        {"updateSheetProperties": {
            "properties": {"sheetId": sid,
                           "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 5000,
                      "startColumnIndex": 2, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {
                "numberFormat": {"type": "NUMBER", "pattern": "#,##0"}}},
            "fields": "userEnteredFormat.numberFormat"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 5000,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "cell": {"userEnteredFormat": {
                "numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
            "fields": "userEnteredFormat.numberFormat"}},
    ]
    for c1, c2, px in lebar.get(ws.title, []):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": c1, "endIndex": c2},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})
    try:
        ss.batch_update({"requests": reqs})
    except Exception as e:
        logger.error(f"Gagal merapikan header {ws.title}: {e}")


def hapus_sheet_bawaan(ss):
    """Hapus Sheet1 bawaan Google kalau memang kosong dan bukan satu-satunya."""
    bawaan = {"sheet1", "sheet 1", "lembar1", "lembar 1"}
    try:
        semua = ss.worksheets()
        if len(semua) <= 1:
            return
        for ws in semua:
            if ws.title.strip().lower() in bawaan and not ws.get_all_values():
                ss.del_worksheet(ws)
                logger.info(f"Sheet bawaan '{ws.title}' dihapus")
                break
    except Exception as e:
        logger.error(f"Gagal hapus sheet bawaan: {e}")


SHEET_GRAFIK = os.environ.get("SHEET_GRAFIK", "Grafik")


def setup_grafik(ss, dash_id):
    """Buat sheet Grafik berisi 3 chart yang menarik data dari Dashboard."""
    try:
        ss.worksheet(SHEET_GRAFIK)
        return False
    except gspread.WorksheetNotFound:
        pass

    ws = ss.add_worksheet(title=SHEET_GRAFIK, rows=120, cols=12)
    gid = ws.id

    def sumber(r1, c1, r2, c2):
        """Rentang data di sheet Dashboard."""
        return {"sources": [{"sheetId": dash_id,
                             "startRowIndex": r1, "endRowIndex": r2,
                             "startColumnIndex": c1, "endColumnIndex": c2}]}

    def posisi(baris):
        return {"overlayPosition": {
            "anchorCell": {"sheetId": gid, "rowIndex": baris, "columnIndex": 0},
            "offsetXPixels": 10, "offsetYPixels": 10,
            "widthPixels": 760, "heightPixels": 380}}

    def sumbu(judul_x, judul_y):
        return [{"position": "BOTTOM_AXIS", "title": judul_x},
                {"position": "LEFT_AXIS", "title": judul_y}]

    # 1. Pie: komposisi pengeluaran per kategori (periode berjalan)
    pie = {"addChart": {"chart": {
        "spec": {
            "title": "Pengeluaran per Kategori — Periode Berjalan",
            "pieChart": {
                "legendPosition": "RIGHT_LEGEND",
                "threeDimensional": False,
                "pieHole": 0.4,
                "domain": {"sourceRange": sumber(9, 0, 40, 1)},   # A10:A40
                "series": {"sourceRange": sumber(9, 1, 40, 2)},   # B10:B40
            }},
        "position": posisi(0)}}}

    # 2. Kolom: pengeluaran harian
    harian = {"addChart": {"chart": {
        "spec": {
            "title": "Pengeluaran Harian",
            "basicChart": {
                "chartType": "COLUMN",
                "legendPosition": "NO_LEGEND",
                "headerCount": 1,
                "axis": sumbu("Tanggal", "Rupiah"),
                "domains": [{"domain": {"sourceRange": sumber(1, 3, 33, 4)}}],
                "series": [{"series": {"sourceRange": sumber(1, 4, 33, 5)},
                            "targetAxis": "LEFT_AXIS"}],
            }},
        "position": posisi(20)}}}

    # 3. Kolom ganda: pemasukan vs pengeluaran tiap periode
    periode = {"addChart": {"chart": {
        "spec": {
            "title": "Pemasukan vs Pengeluaran per Periode",
            "basicChart": {
                "chartType": "COLUMN",
                "legendPosition": "BOTTOM_LEGEND",
                "headerCount": 1,
                "axis": sumbu("Periode", "Rupiah"),
                "domains": [{"domain": {"sourceRange": sumber(1, 6, 20, 7)}}],
                "series": [
                    {"series": {"sourceRange": sumber(1, 8, 20, 9)},
                     "targetAxis": "LEFT_AXIS"},   # Pemasukan
                    {"series": {"sourceRange": sumber(1, 7, 20, 8)},
                     "targetAxis": "LEFT_AXIS"},   # Pengeluaran
                ],
            }},
        "position": posisi(40)}}}

    try:
        ss.batch_update({"requests": [
            pie, harian, periode,
            {"updateSheetProperties": {
                "properties": {"sheetId": gid,
                               "gridProperties": {"hideGridlines": True}},
                "fields": "gridProperties.hideGridlines"}},
        ]})
    except Exception as e:
        logger.error(f"Gagal membuat grafik: {e}")
        return False
    return True


def setup_dashboard(ss):
    """Buat sheet Dashboard berisi ringkasan otomatis.
    Kalau sudah ada, dibiarkan supaya kustomisasi user tidak hilang."""
    try:
        return ss.worksheet(SHEET_DASHBOARD), False
    except gspread.WorksheetNotFound:
        pass

    ws = ss.add_worksheet(title=SHEET_DASHBOARD, rows=300, cols=14)

    sep, colsep = deteksi_pemisah(ss)
    _isi_dashboard(ws, sep, colsep)

    # Verifikasi: kalau sel bantuan K1 error, berarti tebakan pemisah salah.
    # Tulis ulang memakai pemisah satunya.
    try:
        cek = ws.acell("K1", value_render_option="UNFORMATTED_VALUE").value
        if isinstance(cek, str) and cek.startswith("#"):
            alt = (";", "\\") if sep == "," else (",", ",")
            logger.warning(f"Pemisah '{sep}' ditolak, coba '{alt[0]}'")
            _isi_dashboard(ws, alt[0], alt[1])
    except Exception as e:
        logger.error(f"Gagal verifikasi formula dashboard: {e}")

    _rapikan_dashboard(ss, ws)
    return ws, True


# ------------------------------------------
# Daftar user (mapping user_id -> spreadsheet_id)
# ------------------------------------------
_user_map = None  # cache di memori


def get_users_sheet():
    ss = get_client().open_by_key(MASTER_SPREADSHEET_ID)
    return get_or_create_worksheet(ss, USERS_SHEET, HEADER_USERS)


def load_user_map(force=False):
    global _user_map
    if _user_map is not None and not force:
        return _user_map
    mapping = {}
    try:
        rows = get_users_sheet().get_all_records()
        for r in rows:
            uid = str(r.get("user_id", "")).strip()
            sid = str(r.get("spreadsheet_id", "")).strip()
            if uid and sid:
                mapping[uid] = sid
    except Exception as e:
        logger.error(f"Gagal load daftar user: {e}")
    _user_map = mapping
    return _user_map


def simpan_user(user_id, username, spreadsheet_id):
    """Tambah user baru, atau update spreadsheet_id kalau user sudah pernah daftar."""
    ws = get_users_sheet()
    uid = str(user_id)
    try:
        cell = ws.find(uid, in_column=1)
    except Exception:
        cell = None
    tgl = now_wib().strftime("%Y-%m-%d %H:%M")
    if cell:
        ws.update(
            f"A{cell.row}:D{cell.row}",
            [[uid, username or "-", spreadsheet_id, tgl]],
            value_input_option="USER_ENTERED",
        )
    else:
        ws.append_row(
            [uid, username or "-", spreadsheet_id, tgl],
            value_input_option="USER_ENTERED",
        )
    load_user_map(force=True)


def get_spreadsheet_id(user_id):
    return load_user_map().get(str(user_id))


# ------------------------------------------
# Tulis transaksi ke spreadsheet milik user
# ------------------------------------------
def simpan_pengeluaran(user_id, tanggal, kategori, nominal, merchant,
                       sumber, catatan, tipe_bayar, barang=""):
    sid = get_spreadsheet_id(user_id)
    ss = get_client().open_by_key(sid)
    ws = get_or_create_worksheet(ss, SHEET_PENGELUARAN, HEADER_PENGELUARAN)
    ws.append_row(
        [tanggal, kategori, nominal, merchant, sumber, catatan, tipe_bayar, barang],
        value_input_option="USER_ENTERED",
    )


def simpan_pemasukan(user_id, tanggal, kategori, nominal, sumber, catatan):
    sid = get_spreadsheet_id(user_id)
    ss = get_client().open_by_key(sid)
    ws = get_or_create_worksheet(ss, SHEET_PEMASUKAN, HEADER_PEMASUKAN)
    ws.append_row(
        [tanggal, kategori, nominal, sumber, catatan],
        value_input_option="USER_ENTERED",
    )


# ==========================================
# DATA SEMENTARA
# Pakai token unik per transaksi, supaya kirim beberapa struk sekaligus
# tidak saling menimpa (bug versi sebelumnya).
# ==========================================
pending = {}  # token -> dict data


def buat_token(data):
    token = uuid.uuid4().hex[:10]
    pending[token] = data
    if len(pending) > 500:  # jaga-jaga supaya memori tidak menumpuk
        for k in list(pending)[:100]:
            pending.pop(k, None)
    return token


# ==========================================
# KEYBOARD
# ==========================================
def keyboard_tipe_bayar(token):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💵 Cash", callback_data=f"bayar_cash|{token}"),
            InlineKeyboardButton("💳 Pay Later", callback_data=f"bayar_paylater|{token}"),
        ],
        [InlineKeyboardButton("✏️ Ganti Kategori", callback_data=f"editkat|{token}")],
    ])


def keyboard_pilih_kategori(token):
    baris, row = [], []
    for i, k in enumerate(KATEGORI_BAKU):
        row.append(InlineKeyboardButton(k, callback_data=f"setkat_{i}|{token}"))
        if len(row) == 2:
            baris.append(row)
            row = []
    if row:
        baris.append(row)
    return InlineKeyboardMarkup(baris)


def keyboard_konfirmasi_struk(token):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Simpan", callback_data=f"struk_simpan|{token}"),
        InlineKeyboardButton("❌ Batal", callback_data=f"struk_batal|{token}"),
    ]])


KATEGORI_MASUK = {
    "gaji": "💼 Gaji/Tunjangan",
    "freelance": "💸 Freelance",
    "bonus": "🎁 Bonus/THR",
    "investasi": "📈 Investasi",
    "transfer": "🔄 Transfer Masuk",
    "lainnya": "📦 Lainnya",
}


def keyboard_kategori_pemasukan(token):
    keys = list(KATEGORI_MASUK.items())
    rows = []
    for i in range(0, len(keys), 2):
        rows.append([
            InlineKeyboardButton(label, callback_data=f"masuk_{kode}|{token}")
            for kode, label in keys[i:i + 2]
        ])
    return InlineKeyboardMarkup(rows)


# ==========================================
# PANDUAN PENDAFTARAN
# ==========================================
def pesan_belum_daftar():
    return (
        "🔐 Untuk mulai, hubungkan spreadsheet-mu — cuma 3 langkah:\n\n"
        "1️⃣ Buat spreadsheet baru di Google Sheets.\n\n"
        "2️⃣ Klik *Bagikan*, tempel email ini sebagai *Editor* "
        "(ketuk untuk menyalin):\n"
        f"`{SERVICE_ACCOUNT_EMAIL}`\n\n"
        "3️⃣ Tempel *link* spreadsheet-nya ke sini.\n\n"
        "_Kolom, sheet, dan dashboard saya buat otomatis._"
    )


def pesan_cara_manual():
    return (
        "Yuk hubungkan manual, cuma 3 langkah:\n\n"
        "1️⃣ Buat spreadsheet baru di Google Sheets.\n\n"
        "2️⃣ Klik *Bagikan*, tempel email ini sebagai *Editor* "
        "(ketuk untuk menyalin):\n"
        f"`{SERVICE_ACCOUNT_EMAIL}`\n\n"
        "3️⃣ Tempel *link* spreadsheet-nya ke sini."
    )


# ==========================================
# HANDLER: /start
# ==========================================
def keyboard_utama():
    return ReplyKeyboardMarkup(
        [
            ["📝 Catat", "📊 Rekap Hari Ini"],
            ["🤖 Tanya AI", "📈 Dashboard"],
            ["✨ Fitur", "💡 Saran"],
        ],
        resize_keyboard=True,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_spreadsheet_id(user_id):
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return
    await update.message.reply_text(
        "👋 Halo! Saya bot pencatat keuangan kamu.\n\n"
        "📝 *Cara pakai:*\n\n"
        "1️⃣ *Pengeluaran manual*\n"
        "`/catat 50000 Makan nasi goreng kantor`\n"
        "_Tambah note pribadi pakai `;`_ →\n"
        "`/catat 50000 Makan siang tim ; ditalangin, ditagih ke Andi`\n\n"
        "2️⃣ *Pemasukan*\n"
        "`/masuk 5000000 Gaji bulan ini`\n\n"
        "3️⃣ *Dari struk*\n"
        "Kirim foto struk, saya baca otomatis. Kirim satu foto per struk.\n\n"
        "Gunakan *tombol di bawah* untuk akses cepat 👇",
        parse_mode="Markdown",
        reply_markup=keyboard_utama(),
    )


# ==========================================
# INTI PENDAFTARAN (dipakai /daftar & deteksi link otomatis)
# ==========================================
def ekstrak_id_spreadsheet(teks):
    """Ambil ID dari URL /d/<id>, atau dari ID mentah. None kalau tak valid."""
    if not teks:
        return None
    teks = teks.strip()
    m = re.search(r"/d/([a-zA-Z0-9\-_]{20,})", teks)
    if m:
        return m.group(1)
    if re.fullmatch(r"[a-zA-Z0-9\-_]{20,}", teks):
        return teks
    return None


async def _proses_daftar(update, spreadsheet_id, user):
    await update.message.reply_text("🔍 Mengecek akses ke spreadsheet...")

    try:
        ss = get_client().open_by_key(spreadsheet_id)
        judul = ss.title
        ws_out = get_or_create_worksheet(ss, SHEET_PENGELUARAN, HEADER_PENGELUARAN)
        ws_in = get_or_create_worksheet(ss, SHEET_PEMASUKAN, HEADER_PEMASUKAN)
        rapikan_header(ss, ws_out, len(HEADER_PENGELUARAN),
                       {"red": 0.15, "green": 0.35, "blue": 0.55})   # biru tua
        rapikan_header(ss, ws_in, len(HEADER_PEMASUKAN),
                       {"red": 0.13, "green": 0.42, "blue": 0.31})   # hijau tua
        ws_dash, _ = setup_dashboard(ss)
        setup_grafik(ss, ws_dash.id)
        hapus_sheet_bawaan(ss)
    except gspread.SpreadsheetNotFound:
        await update.message.reply_text(
            "❌ Spreadsheet tidak ditemukan atau saya belum diberi akses.\n\n"
            "Pastikan sudah kamu *Bagikan* ke email ini sebagai *Editor*:\n"
            f"`{SERVICE_ACCOUNT_EMAIL}`\n\n"
            "Lalu tempel lagi link-nya.",
            parse_mode="Markdown",
        )
        return
    except Exception as e:
        logger.error(f"Gagal daftar {user.id}: {e}")
        await update.message.reply_text(
            "❌ Gagal menghubungkan spreadsheet. "
            "Cek link dan izin aksesnya, lalu coba lagi."
        )
        return

    try:
        simpan_user(user.id, user.username, spreadsheet_id)
    except Exception as e:
        logger.error(f"Gagal simpan user {user.id}: {e}")
        await update.message.reply_text(
            "❌ Spreadsheet bisa diakses, tapi pendaftaran gagal disimpan. "
            "Coba lagi beberapa saat."
        )
        return

    await update.message.reply_text(
        f"✅ *Berhasil terhubung!*\n\n"
        f"📄 Spreadsheet: *{judul}*\n"
        f"📑 Sheet *{SHEET_PENGELUARAN}*, *{SHEET_PEMASUKAN}*, "
        f"*{SHEET_DASHBOARD}*, dan *{SHEET_GRAFIK}* sudah siap.\n\n"
        f"📊 Dashboard akan terisi sendiri begitu ada transaksi.\n\n"
        f"Coba sekarang:\n`/catat 15000 Makan nasi goreng`",
        parse_mode="Markdown",
        reply_markup=keyboard_utama(),
    )


# ==========================================
# HANDLER: /daftar
# ==========================================
async def daftar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if not args:
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    sid = ekstrak_id_spreadsheet(" ".join(args))
    if not sid:
        await update.message.reply_text(
            "⚠️ Link atau ID-nya sepertinya tidak valid.\n"
            "Tempel *link lengkap* spreadsheet-nya, contoh:\n"
            "`https://docs.google.com/spreadsheets/d/.../edit`",
            parse_mode="Markdown",
        )
        return

    await _proses_daftar(update, sid, user)


# ==========================================
# JALUR CEPAT: bot membuatkan spreadsheet untuk user
# ==========================================
def valid_email(s):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", (s or "").strip()))


async def _buatkan_spreadsheet(update, email, user):
    email = email.strip()
    if not valid_email(email):
        await update.message.reply_text(
            "Email-nya sepertinya tidak valid. Contoh: `namakamu@gmail.com`",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text("⏳ Membuatkan spreadsheet untukmu...")
    try:
        ss = get_client().create(f"Keuangan - {user.username or user.id}")
        ss.share(email, perm_type="user", role="writer")
    except Exception as e:
        logger.error(f"Gagal buatkan spreadsheet {user.id}: {e}")
        await update.message.reply_text(
            "❌ Maaf, aku belum bisa membuatkan otomatis sekarang.\n\n" + pesan_cara_manual(),
            parse_mode="Markdown",
        )
        return

    # Sheet sudah dibuat & di-share. Jalankan setup + simpan lewat alur yang ada.
    await _proses_daftar(update, ss.id, user)
    await update.message.reply_text(
        f"🔗 Ini spreadsheet-mu (sudah ku-share ke {email}):\n"
        f"https://docs.google.com/spreadsheets/d/{ss.id}/edit\n\n"
        f"Buka dari Google Sheets → menu *Dibagikan kepada saya*.",
        parse_mode="Markdown",
    )


async def buatkan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_spreadsheet_id(update.effective_user.id):
        await update.message.reply_text("Kamu sudah terhubung. Cek dengan /info.")
        return
    email = " ".join(context.args).strip()
    if not email:
        await update.message.reply_text(
            "Ketik email Gmail-mu setelah perintah, contoh:\n"
            "`/buatkan namakamu@gmail.com`",
            parse_mode="Markdown",
        )
        return
    await _buatkan_spreadsheet(update, email, update.effective_user)


# ==========================================
# HANDLER: teks biasa (deteksi link tempelan)
# ==========================================
async def terima_teks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alur teks biasa (bukan command):
       1) mode saran  2) link spreadsheet  3) belum daftar -> panduan
       4) sudah daftar -> coba pahami sebagai pencatatan belanja bebas."""
    user_id = update.effective_user.id
    teks = (update.message.text or "").strip()

    # 1. Sedang mode saran?
    if user_id in menunggu_saran:
        menunggu_saran.discard(user_id)
        await _teruskan_saran(update, context, teks=teks)
        return

    # 2. Link spreadsheet -> daftarkan
    if "spreadsheets" in teks.lower():
        sid = ekstrak_id_spreadsheet(teks)
        if sid:
            await _proses_daftar(update, sid, update.effective_user)
            return

    # 3. Belum terdaftar -> panduan manual
    if not get_spreadsheet_id(user_id):
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    # 4. Terdaftar -> tombol keyboard, query rekap, atau catat belanja
    if not teks:
        return

    # Tombol keyboard utama
    if teks == "📊 Rekap Hari Ini":
        await _proses_rekap(update, "hari ini", user_id)
        return
    if teks == "✨ Fitur":
        await update.message.reply_text(TEKS_FITUR, parse_mode="Markdown")
        return
    if teks == "📈 Dashboard":
        await info(update, context)
        return
    if teks == "💡 Saran":
        menunggu_saran.add(user_id)
        await update.message.reply_text(
            "💡 Silakan kirim saranmu — boleh *teks*, atau *foto beserta caption*.\n"
            "Ketik /batal untuk membatalkan.",
            parse_mode="Markdown",
        )
        return
    if teks == "🤖 Tanya AI":
        await update.message.reply_text(
            "Ketik pertanyaanmu, contoh:\n"
            "`/tanya berapa kali saya ngopi minggu ini`\n"
            "`/tanya beri saran biar lebih hemat`",
            parse_mode="Markdown",
        )
        return
    if teks == "📝 Catat":
        await update.message.reply_text(
            "Ketik pengeluaranmu langsung, contoh:\n"
            "\"jajan bakso 20rb di warung Ali\"\n"
            "atau `/catat 20000 Makan bakso`",
            parse_mode="Markdown",
        )
        return

    low = teks.lower()
    if low.startswith(("transaksi", "rekap", "laporan", "riwayat", "lihat")):
        await _proses_rekap(update, teks, user_id)
    else:
        await _proses_teks_belanja(update, teks, user_id)


async def _proses_teks_belanja(update, teks, user_id):
    """Urai kalimat bebas (mis. 'jajan bakso 20rb di warung Ali') jadi transaksi."""
    # Deteksi 'kemarin'/'kemarin lusa' dulu, lalu buang kata waktunya
    # supaya tidak ikut mengganggu parser.
    tanggal, sisa_tok = tanggal_dari_kata(teks.split())
    teks_bersih = " ".join(sisa_tok) or teks
    hari_ini = now_wib().strftime("%Y-%m-%d")
    prompt = f"""Ubah kalimat belanja berikut jadi JSON. Hari ini {hari_ini}.
Kalimat: "{teks_bersih}"

Balas HANYA JSON, tanpa markdown, bentuk:
{{"nominal": angka_tanpa_titik, "kategori": "salah satu dari: Makan, Donasi, Transport, Belanja, Hiburan, Tagihan, Investasi, Lainnya", "merchant": "nama toko/tempat atau '-'", "items": "daftar barang pisah koma atau ''"}}

Aturan:
- nominal rupiah: "20rb"/"20 ribu" = 20000, "1,5jt"/"1.5 juta" = 1500000.
- Kalau kalimat BUKAN pencatatan belanja/pengeluaran (mis. pertanyaan, sapaan, perintah), balas {{"nominal": 0}}."""
    try:
        resp = gemini_model.generate_content(prompt)
        raw = (resp.text or "").strip().replace("```json", "").replace("```", "").strip()
        hasil = json.loads(raw)
    except Exception as e:
        logger.error(f"parse teks belanja: {e}")
        await update.message.reply_text(
            "Hmm, aku belum paham 🤔\n"
            "Untuk mencatat pengeluaran: ketik `/catat` atau langsung "
            "seperti \"jajan bakso 20rb\".\n"
            "Untuk bertanya soal keuangan: `/tanya`.",
            parse_mode="Markdown",
        )
        return

    try:
        nominal = int(hasil.get("nominal") or 0)
    except (ValueError, TypeError):
        nominal = 0

    if nominal <= 0:
        await update.message.reply_text(
            "Kalau mau mencatat pengeluaran, sebutkan nominalnya ya.\n"
            "Contoh: \"jajan bakso 20rb di warung Ali\"\n\n"
            "Mau tanya soal keuangan? Pakai /tanya. Punya masukan? /saran."
        )
        return

    kategori = normalkan_kategori(
        hasil.get("kategori", "Lainnya"), hasil.get("merchant", ""), paksa=True
    )
    data = {
        "user_id": user_id,
        "jenis": "pengeluaran",
        "tanggal": tanggal,
        "kategori": kategori,
        "nominal": nominal,
        "merchant": (hasil.get("merchant") or "-").strip() or "-",
        "sumber": "Teks",
        "catatan": "",
        "barang": (hasil.get("items") or "").strip(),
    }
    token = buat_token(data)
    await update.message.reply_text(
        f"📋 *Detail Pengeluaran:*\n\n"
        f"🏪 Merchant: {data['merchant']}\n"
        f"📅 Tanggal: {data['tanggal']}\n"
        f"🏷️ Kategori: {data['kategori']}\n"
        f"🛒 Barang: {data['barang'] or '-'}\n"
        f"💰 Nominal: Rp{nominal:,}\n\n"
        f"Pilih tipe pembayaran:",
        parse_mode="Markdown",
        reply_markup=keyboard_tipe_bayar(token),
    )


# ==========================================
# HANDLER: /info
# ==========================================
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sid = get_spreadsheet_id(update.effective_user.id)
    if not sid:
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return
    try:
        judul = get_client().open_by_key(sid).title
    except Exception:
        judul = "(tidak bisa diakses — cek izin share)"
    await update.message.reply_text(
        f"📄 Spreadsheet terhubung: *{judul}*\n"
        f"🔗 https://docs.google.com/spreadsheets/d/{sid}/edit\n\n"
        f"Mau ganti spreadsheet? Tempel link spreadsheet baru di sini.",
        parse_mode="Markdown",
    )


# ==========================================
# HANDLER: /dummy dan /hapusdummy (untuk uji coba)
# ==========================================
def _tanggal_periode(offset_hari):
    from datetime import timedelta
    return (now_wib() - timedelta(days=offset_hari)).strftime("%Y-%m-%d")


DUMMY_PENGELUARAN = [
    (1, "Makan", 25000, "Warteg Bahari", "Nasi Ayam", "Cash"),
    (2, "Transport", 12000, "Gojek", "Ke Kantor", "Pay Later"),
    (3, "Makan", 43500, "BreadTalk", "Roti", "Cash"),
    (5, "Belanja", 87000, "Indomaret", "Belanja Bulanan", "Cash"),
    (7, "Makan", 18000, "Fore Coffee", "Kopi", "Pay Later"),
    (9, "Tagihan", 150000, "PLN", "Listrik", "Cash"),
    (12, "Transport", 3000, "KRL", "Stasiun Bogor", "Cash"),
    (16, "Makan", 65000, "Shabu Hachi", "Makan Siang", "Pay Later"),
    (22, "Belanja", 45000, "Tokopedia", "Aksesoris", "Pay Later"),
    (28, "Makan", 30000, "Kopi Kenangan", "Nongkrong", "Cash"),
    (34, "Transport", 8000, "Parkir", "Mall", "Cash"),
    (40, "Lainnya", 20000, "Barbershop", "Cukur Rambut", "Cash"),
]

DUMMY_PEMASUKAN = [
    (2, "💼 Gaji/Tunjangan", 5500000, "Gaji Bulan Ini"),
    (10, "💸 Freelance", 750000, "Proyek Desain"),
    (33, "💼 Gaji/Tunjangan", 5500000, "Gaji Bulan Lalu"),
    (38, "🎁 Bonus/THR", 300000, "Bonus Kinerja"),
]


async def dummy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sid = get_spreadsheet_id(user_id)
    if not sid:
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    await update.message.reply_text("🧪 Membuat data contoh...")
    try:
        ss = get_client().open_by_key(sid)
        ws_out = get_or_create_worksheet(ss, SHEET_PENGELUARAN, HEADER_PENGELUARAN)
        ws_in = get_or_create_worksheet(ss, SHEET_PEMASUKAN, HEADER_PEMASUKAN)

        baris_out = [[_tanggal_periode(h), kat, nom, mer, "Dummy", cat, tipe]
                     for h, kat, nom, mer, cat, tipe in DUMMY_PENGELUARAN]
        baris_in = [[_tanggal_periode(h), kat, nom, "Dummy", cat]
                    for h, kat, nom, cat in DUMMY_PEMASUKAN]

        ws_out.append_rows(baris_out, value_input_option="USER_ENTERED")
        ws_in.append_rows(baris_in, value_input_option="USER_ENTERED")

        await update.message.reply_text(
            f"✅ *Data contoh dibuat*\n\n"
            f"📤 {len(baris_out)} pengeluaran\n"
            f"📥 {len(baris_in)} pemasukan\n"
            f"Tersebar di periode ini dan periode sebelumnya.\n\n"
            f"Buka sheet *{SHEET_DASHBOARD}* untuk melihat hasilnya.\n"
            f"Hapus lagi dengan `/hapusdummy`",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Gagal buat dummy {user_id}: {e}")
        await update.message.reply_text("❌ Gagal membuat data contoh.")


def _hapus_baris_dummy(ss, nama_sheet, kolom_sumber, header):
    """Hapus semua baris yang kolom Sumber-nya bertuliskan 'Dummy'."""
    ws = get_or_create_worksheet(ss, nama_sheet, header)
    semua = ws.get_all_values()
    target = [i for i, r in enumerate(semua)
              if i > 0 and len(r) > kolom_sumber and r[kolom_sumber] == "Dummy"]
    if not target:
        return 0
    reqs = []
    for i in sorted(target, reverse=True):  # dari bawah, supaya indeks tidak geser
        reqs.append({"deleteDimension": {"range": {
            "sheetId": ws.id, "dimension": "ROWS",
            "startIndex": i, "endIndex": i + 1}}})
    ss.batch_update({"requests": reqs})
    return len(target)


async def hapusdummy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sid = get_spreadsheet_id(user_id)
    if not sid:
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    await update.message.reply_text("🧹 Menghapus data contoh...")
    try:
        ss = get_client().open_by_key(sid)
        n1 = _hapus_baris_dummy(ss, SHEET_PENGELUARAN, 4, HEADER_PENGELUARAN)
        n2 = _hapus_baris_dummy(ss, SHEET_PEMASUKAN, 3, HEADER_PEMASUKAN)
        await update.message.reply_text(
            f"✅ Data contoh dihapus.\n"
            f"📤 {n1} pengeluaran, 📥 {n2} pemasukan.\n\n"
            f"Data asli kamu tidak tersentuh."
        )
    except Exception as e:
        logger.error(f"Gagal hapus dummy {user_id}: {e}")
        await update.message.reply_text("❌ Gagal menghapus data contoh.")


# ==========================================
# HANDLER: /catat
# ==========================================
def tanggal_dari_kata(tokens):
    """Deteksi kata waktu di antara tokens dan buang katanya.
    Kembalikan (tanggal 'YYYY-MM-DD', tokens_bersih).
      'kemarin'       -> mundur 1 hari
      'kemarin lusa'  -> mundur 2 hari
    Kalau tidak ada, tanggalnya hari ini."""
    from datetime import timedelta
    offset = 0
    bersih = []
    low = [t.lower() for t in tokens]
    i = 0
    while i < len(tokens):
        if low[i] == "kemarin":
            if i + 1 < len(tokens) and low[i + 1] == "lusa":
                offset = 2
                i += 2
                continue
            offset = 1
            i += 1
            continue
        bersih.append(tokens[i])
        i += 1
    tgl = (now_wib() - timedelta(days=offset)).strftime("%Y-%m-%d")
    return tgl, bersih


async def catat_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_spreadsheet_id(user_id):
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "⚠️ Format salah.\n\n"
            "Contoh: `/catat 50000 Makan nasi goreng`\n"
            "Format: /catat [nominal] [kategori] [catatan opsional]",
            parse_mode="Markdown",
        )
        return

    try:
        nominal = int(args[0].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("⚠️ Nominal harus angka. Contoh: /catat 50000 Makan")
        return

    # Pisahkan note pribadi (setelah ';') dari kategori + deskripsi.
    kiri, _, note = " ".join(args[1:]).partition(";")
    note = note.strip()

    # Deteksi 'kemarin' hanya di bagian kiri, bukan di dalam note.
    tanggal, sisa = tanggal_dari_kata(kiri.split())
    if not sisa:
        await update.message.reply_text(
            "⚠️ Kategori belum ada.\n\n"
            "Contoh: `/catat 50000 Makan nasi goreng`\n"
            "Tanggal kemarin: `/catat 50000 Makan warteg kemarin`\n"
            "Dengan note: `/catat 50000 Makan siang tim ; ditalangin, ditagih ke Andi`",
            parse_mode="Markdown",
        )
        return

    deskripsi = " ".join(sisa[1:]).strip()          # verbatim, tanpa Title Case
    catatan = " — ".join(p for p in (deskripsi, note) if p)

    data = {
        "user_id": user_id,
        "jenis": "pengeluaran",
        "tanggal": tanggal,
        "kategori": normalkan_kategori(sisa[0]),
        "nominal": nominal,
        "merchant": "-",
        "sumber": "Manual",
        "catatan": catatan,
    }
    token = buat_token(data)

    await update.message.reply_text(
        f"📋 *Detail Pengeluaran:*\n\n"
        f"📅 Tanggal: {data['tanggal']}\n"
        f"🏷️ Kategori: {data['kategori']}\n"
        f"💰 Nominal: Rp{nominal:,}\n"
        f"📝 Catatan: {data['catatan'] or '-'}\n\n"
        f"Pilih tipe pembayaran:",
        parse_mode="Markdown",
        reply_markup=keyboard_tipe_bayar(token),
    )


# ==========================================
# HANDLER: /masuk
# ==========================================
async def catat_masuk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_spreadsheet_id(user_id):
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text(
            "⚠️ Format salah.\n\n"
            "Contoh: `/masuk 5000000 Gaji bulan ini`\n"
            "Format: /masuk [nominal] [catatan opsional]",
            parse_mode="Markdown",
        )
        return

    try:
        nominal = int(args[0].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("⚠️ Nominal harus angka. Contoh: /masuk 5000000")
        return

    kiri, _, note = " ".join(args[1:]).partition(";")
    note = note.strip()
    tanggal, sisa = tanggal_dari_kata(kiri.split())
    deskripsi = " ".join(sisa).strip()              # verbatim, tanpa Title Case
    catatan = " — ".join(p for p in (deskripsi, note) if p)

    data = {
        "user_id": user_id,
        "jenis": "pemasukan",
        "tanggal": tanggal,
        "nominal": nominal,
        "catatan": catatan,
    }
    token = buat_token(data)

    await update.message.reply_text(
        f"📋 *Detail Pemasukan:*\n\n"
        f"📅 Tanggal: {data['tanggal']}\n"
        f"💰 Nominal: Rp{nominal:,}\n"
        f"📝 Catatan: {data['catatan'] or '-'}\n\n"
        f"Pilih kategori pemasukan:",
        parse_mode="Markdown",
        reply_markup=keyboard_kategori_pemasukan(token),
    )


# ==========================================
# HANDLER: /hapus (hapus transaksi pengeluaran terakhir)
# ==========================================
async def hapus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sid = get_spreadsheet_id(user_id)
    if not sid:
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    try:
        ws = get_client().open_by_key(sid).worksheet(SHEET_PENGELUARAN)
        nilai = ws.get_all_values()
    except Exception as e:
        logger.error(f"hapus baca sheet {user_id}: {e}")
        await update.message.reply_text("❌ Gagal membaca data.")
        return

    idx, baris = None, None
    for i in range(len(nilai) - 1, 0, -1):   # lewati header (baris 1)
        if nilai[i] and nilai[i][0]:
            idx, baris = i + 1, nilai[i]     # idx 1-based untuk delete_rows
            break

    if not idx:
        await update.message.reply_text("Belum ada pengeluaran untuk dihapus.")
        return

    token = buat_token({"user_id": user_id, "hapus_row": idx})
    nom = re.sub(r"[^\d]", "", str(baris[2])) if len(baris) > 2 else "0"
    await update.message.reply_text(
        f"🗑️ *Hapus pengeluaran terakhir ini?*\n\n"
        f"📅 {baris[0]}\n"
        f"🏷️ {baris[1] if len(baris) > 1 else '-'}\n"
        f"💰 Rp{int(nom or 0):,}\n"
        f"🏪 {baris[3] if len(baris) > 3 else '-'}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🗑️ Ya, hapus", callback_data=f"hapus_ya|{token}"),
            InlineKeyboardButton("❌ Batal", callback_data=f"hapus_batal|{token}"),
        ]]),
    )


# ==========================================
# Cek duplikat & rekap transaksi
# ==========================================
def is_pertanyaan_cek(caption):
    """True kalau caption terlihat seperti pertanyaan 'sudah pernah diupload?'."""
    c = (caption or "").lower()
    if not c:
        return False
    tanya = ("?" in c) or c.startswith("apakah")
    kunci = ("sudah", "pernah", "duplikat", "belum", "double", "dobel",
             "upload", "input", "diinput", "dicatat", "masuk")
    return tanya and any(k in c for k in kunci)


def cari_duplikat(sid, tanggal, nominal):
    """Cari baris pengeluaran dengan tanggal & nominal sama. Return list dict."""
    try:
        ss = get_client().open_by_key(sid)
        nilai = ss.worksheet(SHEET_PENGELUARAN).get_all_values()[1:]
    except Exception as e:
        logger.error(f"cek duplikat: {e}")
        return []
    target = re.sub(r"[^\d]", "", str(nominal))
    cocok = []
    for r in nilai:
        if len(r) < 3 or not r[0]:
            continue
        if str(r[0])[:10] == str(tanggal)[:10] and re.sub(r"[^\d]", "", str(r[2])) == target:
            cocok.append({
                "kategori": r[1] if len(r) > 1 else "",
                "merchant": r[3] if len(r) > 3 else "",
                "catatan": r[5] if len(r) > 5 else "",
            })
    return cocok


async def _proses_rekap(update, periode_teks, user_id):
    """Tampilkan daftar transaksi pada periode yang diminta user."""
    sid = get_spreadsheet_id(user_id)
    if not sid:
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    hari_ini = now_wib().strftime("%Y-%m-%d")
    prompt = f"""Ubah deskripsi periode ini jadi rentang tanggal. Hari ini {hari_ini}.
Deskripsi: "{periode_teks}"

Balas HANYA JSON: {{"start":"YYYY-MM-DD","end":"YYYY-MM-DD","tipe":"paylater / cash / (kosong)"}}
Aturan:
- "1 agustus 2026" -> start=end=2026-08-01
- "hari ini" -> {hari_ini}; "kemarin" -> sehari sebelum {hari_ini}
- "minggu ini" -> Senin s/d Minggu minggu ini
- "bulan ini" -> tanggal 1 s/d akhir bulan ini
- kalau tak jelas, pakai {hari_ini} untuk start & end.
- "tipe": isi "paylater" kalau user menyebut pay later/paylater/cicilan;
  "cash"/"tunai" kalau menyebut cash/tunai; selain itu kosongkan ("")."""
    try:
        resp = gemini_model.generate_content(prompt)
        raw = re.sub(r"^```json\s*|\s*```$", "", resp.text.strip()).strip()
        rng = json.loads(raw)
        start, end = rng["start"], rng["end"]
        tipe_f = (rng.get("tipe") or "").lower().replace(" ", "")
    except Exception as e:
        logger.error(f"parse periode rekap: {e}")
        await update.message.reply_text(
            "Aku belum paham periodenya 🤔\n"
            "Contoh: `/rekap 1 agustus 2026`, `/rekap minggu ini`, `/rekap bulan ini`.",
            parse_mode="Markdown",
        )
        return

    try:
        ss = get_client().open_by_key(sid)
        out = ss.worksheet(SHEET_PENGELUARAN).get_all_values()[1:]
        try:
            inc = ss.worksheet(SHEET_PEMASUKAN).get_all_values()[1:]
        except Exception:
            inc = []
    except Exception as e:
        logger.error(f"baca rekap: {e}")
        await update.message.reply_text("❌ Gagal membaca data.")
        return

    def in_range(tgl):
        return start <= str(tgl)[:10] <= end

    def cocok_tipe(r):
        if not tipe_f:
            return True
        tv = (r[6].lower() if len(r) > 6 else "")
        if tipe_f == "paylater":
            return "paylater" in tv or ("pay" in tv and "later" in tv)
        if tipe_f == "cash":
            return "cash" in tv or "tunai" in tv
        return True

    baris_out, total_out = [], 0
    for r in out:
        if r and r[0] and in_range(r[0]) and cocok_tipe(r):
            nom = int(re.sub(r"[^\d]", "", str(r[2])) or 0)
            total_out += nom
            ket = (r[3] if len(r) > 3 and r[3] not in ("", "-") else
                   (r[1] if len(r) > 1 else ""))
            baris_out.append(f"• {str(r[0])[:10]} · Rp{nom:,} — {ket}")

    # Pemasukan tak punya tipe bayar; sembunyikan kalau user memfilter tipe.
    baris_in, total_in = [], 0
    if not tipe_f:
        for r in inc:
            if r and r[0] and in_range(r[0]):
                nom = int(re.sub(r"[^\d]", "", str(r[2])) or 0)
                total_in += nom
                baris_in.append(f"• {str(r[0])[:10]} · Rp{nom:,} — {r[1] if len(r) > 1 else ''}")

    label_tipe = {"paylater": " (Pay Later)", "cash": " (Cash)"}.get(tipe_f, "")
    judul = f"📊 Rekap {start}" + (f" s/d {end}" if end != start else "") + label_tipe
    bagian = [judul, ""]
    if baris_out:
        bagian.append(f"📤 Pengeluaran ({len(baris_out)}x) — total Rp{total_out:,}")
        bagian += baris_out
    else:
        bagian.append("📤 Tidak ada pengeluaran" + (label_tipe or "") + ".")
    if baris_in:
        bagian.append("")
        bagian.append(f"📥 Pemasukan ({len(baris_in)}x) — total Rp{total_in:,}")
        bagian += baris_in

    await update.message.reply_text("\n".join(bagian)[:4000])


async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    periode = " ".join(context.args).strip() or "hari ini"
    await _proses_rekap(update, periode, update.effective_user.id)


# ==========================================
# HANDLER: foto struk
# ==========================================
async def terima_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    caption = (update.message.caption or "").strip()
    photo_id = update.message.photo[-1].file_id

    # Foto sebagai SARAN: mode saran aktif, atau caption diawali /saran.
    if user_id in menunggu_saran or caption.lower().startswith("/saran"):
        menunggu_saran.discard(user_id)
        if caption.lower().startswith("/saran"):
            p = caption.split(maxsplit=1)
            caption = p[1].strip() if len(p) > 1 else ""
        await _teruskan_saran(update, context, teks=caption, photo_id=photo_id)
        return

    if not get_spreadsheet_id(user_id):
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    await update.message.reply_text("📸 Struk diterima, sedang dibaca...")
    hari_ini = now_wib().strftime("%Y-%m-%d")

    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()

        prompt = f"""
        Kamu adalah asisten yang membaca struk belanja/pembayaran.
        Hari ini adalah {hari_ini}. Gunakan ini sebagai acuan tahun,
        JANGAN menebak tahun lain kecuali struk mencantumkan tahun dengan jelas.

        Baca gambar struk ini dan balas dengan JSON saja, tanpa teks lain,
        tanpa markdown backticks:

        {{
            "merchant": "nama toko/tempat",
            "tanggal": "YYYY-MM-DD (kalau tidak jelas gunakan {hari_ini})",
            "nominal": angka_total_tanpa_titik_atau_koma,
            "items": "daftar barang yang dibeli, pisahkan dengan koma (kalau tidak jelas isi '')",
            "kategori": "WAJIB pilih SATU dari: Makan, Donasi, Transport, Belanja, Hiburan, Tagihan, Investasi, Lainnya"
        }}

        Panduan memilih kategori (tebak dari nama merchant/isi struk):
        - Makan: makanan & minuman (warteg, kebab, bakso, kopi, Fore, juice, boba)
        - Donasi: sedekah, zakat, infaq, wakaf, sumbangan, kurban, amal
        - Transport: bensin/SPBU, parkir, ojek online, KRL/MRT, tol
        - Belanja: minimarket & toko online (Alfamart, Tokopedia, Shopee, Skintific, jastip)
        - Hiburan: warnet/game center, bioskop, langganan hiburan
        - Tagihan: listrik/PLN, pulsa/data, Apple/Google, cicilan, Pay Later
        - Investasi: Indodax, kripto, reksadana, saham, emas
        - Lainnya: hanya jika benar-benar tidak masuk kategori mana pun

        Ambil TOTAL akhir yang dibayar.
        Jika gambar berisi LEBIH DARI SATU struk, isi nominal dengan -1.
        Jika gambar tidak jelas atau bukan struk, isi nominal dengan 0.
        """

        response = gemini_model.generate_content(
            [prompt, {"mime_type": "image/jpeg", "data": bytes(photo_bytes)}]
        )
        teks = re.sub(r"^```json\s*|\s*```$", "", response.text.strip()).strip()
        hasil = json.loads(teks)
        nominal = hasil.get("nominal", 0)

        if nominal == -1:
            await update.message.reply_text(
                "⚠️ Sepertinya ada beberapa struk dalam satu gambar.\n"
                "Kirim satu foto untuk satu struk ya, supaya nominalnya akurat."
            )
            return

        if not nominal or nominal == 0:
            await update.message.reply_text(
                "⚠️ Struk tidak terbaca jelas.\n"
                "Coba foto ulang lebih dekat, atau catat manual:\n"
                "`/catat 50000 Makan catatan`",
                parse_mode="Markdown",
            )
            return

        data = {
            "user_id": user_id,
            "jenis": "pengeluaran",
            "tanggal": hasil.get("tanggal") or hari_ini,
            "kategori": normalkan_kategori(
                hasil.get("kategori", "Lainnya"),
                hasil.get("merchant", ""),
                paksa=True,
            ),
            "barang": (hasil.get("items") or "").strip(),
            "nominal": nominal,
            "merchant": hasil.get("merchant", "-"),
            "sumber": "Struk",
            "catatan": "" if is_pertanyaan_cek(caption) else (update.message.caption or "").strip(),
        }
        token = buat_token(data)

        # Kalau caption berupa pertanyaan "sudah pernah diupload?", cek dulu.
        if is_pertanyaan_cek(caption):
            dup = cari_duplikat(get_spreadsheet_id(user_id), data["tanggal"], nominal)
            if dup:
                rincian = "\n".join(
                    f"• {d['kategori']} — {d['merchant'] or '-'}"
                    + (f" ({d['catatan']})" if d['catatan'] else "")
                    for d in dup[:5]
                )
                await update.message.reply_text(
                    f"✅ *Sudah pernah dicatat.*\n\n"
                    f"Ada {len(dup)} transaksi dengan tanggal & nominal sama "
                    f"(Rp{nominal:,}, {data['tanggal']}):\n{rincian}\n\n"
                    f"Kalau ini transaksi *berbeda*, kamu tetap bisa menyimpannya:",
                    parse_mode="Markdown",
                    reply_markup=keyboard_konfirmasi_struk(token),
                )
            else:
                await update.message.reply_text(
                    f"🆕 *Belum pernah dicatat.*\n\n"
                    f"🏪 {data['merchant']}\n"
                    f"📅 {data['tanggal']}\n"
                    f"🏷️ {data['kategori']}\n"
                    f"💰 Rp{nominal:,}\n\n"
                    f"Mau simpan transaksi ini?",
                    parse_mode="Markdown",
                    reply_markup=keyboard_konfirmasi_struk(token),
                )
            return

        await update.message.reply_text(
            f"📋 *Hasil baca struk:*\n\n"
            f"🏪 Merchant: {data['merchant']}\n"
            f"📅 Tanggal: {data['tanggal']}\n"
            f"🏷️ Kategori: {data['kategori']}\n"
            f"💰 Nominal: Rp{nominal:,}\n"
            f"📝 Catatan: {data['catatan'] or '-'}\n\n"
            f"Simpan data ini?",
            parse_mode="Markdown",
            reply_markup=keyboard_konfirmasi_struk(token),
        )

    except Exception as e:
        logger.error(f"Gagal proses struk: {e}")
        await update.message.reply_text(
            "❌ Gagal membaca struk. Coba lagi atau catat manual dengan /catat"
        )


# ==========================================
# HANDLER: tombol
# ==========================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    raw = query.data or ""
    aksi, _, token = raw.partition("|")
    data = pending.get(token)

    if not data:
        await query.edit_message_text(
            "⚠️ Data ini sudah kedaluwarsa (bot mungkin baru restart). "
            "Coba input ulang ya."
        )
        return

    # Pastikan yang menekan tombol adalah pemilik data
    if data.get("user_id") != query.from_user.id:
        return

    user_id = data["user_id"]

    # --- Hapus transaksi terakhir ---
    if aksi == "hapus_batal":
        pending.pop(token, None)
        await query.edit_message_text("Dibatalkan. Transaksi tidak jadi dihapus.")
        return
    if aksi == "hapus_ya":
        try:
            ws = get_client().open_by_key(get_spreadsheet_id(user_id)).worksheet(SHEET_PENGELUARAN)
            ws.delete_rows(int(data["hapus_row"]))
            pending.pop(token, None)
            await query.edit_message_text("🗑️ Transaksi terakhir sudah dihapus.")
        except Exception as e:
            logger.error(f"Gagal hapus transaksi {user_id}: {e}")
            await query.edit_message_text("❌ Gagal menghapus. Coba lagi sebentar.")
        return

    # --- Ganti kategori sebelum simpan ---
    if aksi == "editkat":
        await query.edit_message_text(
            f"Pilih kategori baru untuk pengeluaran Rp{data['nominal']:,}:",
            reply_markup=keyboard_pilih_kategori(token),
        )
        return
    if aksi.startswith("setkat_"):
        try:
            data["kategori"] = KATEGORI_BAKU[int(aksi.replace("setkat_", ""))]
        except (ValueError, IndexError):
            pass
        await query.edit_message_text(
            f"📋 *Detail Pengeluaran:*\n\n"
            f"🏪 Merchant: {data.get('merchant', '-')}\n"
            f"📅 Tanggal: {data['tanggal']}\n"
            f"🏷️ Kategori: {data['kategori']}\n"
            f"🛒 Barang: {data.get('barang') or '-'}\n"
            f"💰 Nominal: Rp{data['nominal']:,}\n\n"
            f"Pilih tipe pembayaran:",
            parse_mode="Markdown",
            reply_markup=keyboard_tipe_bayar(token),
        )
        return

    # --- Batal ---
    if aksi == "struk_batal":
        pending.pop(token, None)
        await query.edit_message_text("❌ Dibatalkan, data tidak disimpan.")
        return

    # --- Konfirmasi struk, lanjut pilih tipe bayar ---
    if aksi == "struk_simpan":
        await query.edit_message_text(
            f"📋 *Detail Pengeluaran:*\n\n"
            f"🏪 Merchant: {data['merchant']}\n"
            f"📅 Tanggal: {data['tanggal']}\n"
            f"🏷️ Kategori: {data['kategori']}\n"
            f"🛒 Barang: {data.get('barang') or '-'}\n"
            f"💰 Nominal: Rp{data['nominal']:,}\n\n"
            f"Pilih tipe pembayaran:",
            parse_mode="Markdown",
            reply_markup=keyboard_tipe_bayar(token),
        )
        return

    # --- Tipe pembayaran ---
    if aksi in ("bayar_cash", "bayar_paylater"):
        tipe = "Cash" if aksi == "bayar_cash" else "Pay Later"
        ikon = "💵" if aksi == "bayar_cash" else "💳"
        try:
            simpan_pengeluaran(
                user_id=user_id,
                tanggal=data["tanggal"],
                kategori=data["kategori"],
                nominal=data["nominal"],
                merchant=data.get("merchant", "-"),
                sumber=data.get("sumber", "Manual"),
                catatan=data.get("catatan", ""),
                tipe_bayar=tipe,
                barang=data.get("barang", ""),
            )
            pending.pop(token, None)
            await query.edit_message_text(
                f"✅ *Pengeluaran tersimpan!*\n\n"
                f"📅 {data['tanggal']}\n"
                f"🏷️ {data['kategori']}\n"
                f"💰 Rp{data['nominal']:,}\n"
                f"{ikon} Tipe: *{tipe}*",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Gagal simpan pengeluaran {user_id}: {e}")
            await query.edit_message_text(
                "❌ Gagal menyimpan ke spreadsheet. "
                "Cek apakah akses Editor masih aktif, lalu coba lagi."
            )
        return

    # --- Kategori pemasukan ---
    if aksi.startswith("masuk_"):
        kode = aksi.replace("masuk_", "")
        kategori = KATEGORI_MASUK.get(kode, "📦 Lainnya")
        try:
            simpan_pemasukan(
                user_id=user_id,
                tanggal=data["tanggal"],
                kategori=kategori,
                nominal=data["nominal"],
                sumber="Manual",
                catatan=data.get("catatan", ""),
            )
            pending.pop(token, None)
            await query.edit_message_text(
                f"✅ *Pemasukan tersimpan!*\n\n"
                f"📅 {data['tanggal']}\n"
                f"{kategori}\n"
                f"💰 Rp{data['nominal']:,}\n"
                f"📝 {data.get('catatan') or '-'}",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Gagal simpan pemasukan {user_id}: {e}")
            await query.edit_message_text(
                "❌ Gagal menyimpan ke spreadsheet. "
                "Cek akses Editor, lalu coba lagi."
            )
        return


# ==========================================
# ERROR HANDLER
# ==========================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"!!! ERROR: {context.error}", exc_info=context.error)


# ==========================================
# MAIN
# ==========================================
def cek_konfigurasi():
    """Pastikan semua environment variable wajib sudah diisi."""
    wajib = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "MASTER_SPREADSHEET_ID": MASTER_SPREADSHEET_ID,
        "GOOGLE_CREDENTIALS_JSON": GOOGLE_CREDENTIALS_JSON,
    }
    kurang = [k for k, v in wajib.items() if not v]
    if kurang:
        print("\n[!] Environment variable belum diisi: " + ", ".join(kurang))
        print("    Isi dulu di Railway/VPS, lalu jalankan lagi.\n")
        raise SystemExit(1)


# ==========================================
# AI: tanya-jawab & analisa atas data user
# ==========================================
def data_untuk_ai(sid, batas=800):
    """Ambil transaksi user jadi teks ringkas untuk dianalisis AI.
    Format tiap baris: tanggal|OUT/IN|kategori|nominal|merchant|catatan|tipe_bayar"""
    ss = get_client().open_by_key(sid)
    baris = []
    try:
        out = ss.worksheet(SHEET_PENGELUARAN).get_all_values()[1:]  # tanpa header
        for r in out[-batas:]:
            g = lambda i: r[i] if len(r) > i else ""
            baris.append(f"{g(0)}|OUT|{g(1)}|{g(2)}|{g(3)}|{g(5)}|{g(6)}")
    except Exception as e:
        logger.error(f"AI baca pengeluaran: {e}")
    try:
        inc = ss.worksheet(SHEET_PEMASUKAN).get_all_values()[1:]
        for r in inc[-batas:]:
            g = lambda i: r[i] if len(r) > i else ""
            baris.append(f"{g(0)}|IN|{g(1)}|{g(2)}||{g(4)}|")
    except Exception as e:
        logger.error(f"AI baca pemasukan: {e}")
    return "\n".join(baris)


async def tanya(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sid = get_spreadsheet_id(user_id)
    if not sid:
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    pertanyaan = " ".join(context.args).strip()
    if not pertanyaan:
        await update.message.reply_text(
            "❓ Tanya apa saja soal keuanganmu.\n\n"
            "Contoh:\n"
            "`/tanya berapa kali saya ngopi minggu ini`\n"
            "`/tanya total uang untuk kopi bulan ini`\n"
            "`/tanya berapa kali saya main warnet`\n"
            "`/tanya beri saran biar lebih hemat`",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text("🤔 Menganalisis datamu...")
    try:
        data = data_untuk_ai(sid)
        if not data.strip():
            await update.message.reply_text("Belum ada transaksi untuk dianalisis.")
            return

        hari_ini = now_wib().strftime("%Y-%m-%d")
        prompt = f"""Kamu asisten keuangan pribadi. Hari ini {hari_ini}.
Di bawah ini data transaksi user, satu baris per transaksi dengan format:
tanggal|OUT/IN|kategori|nominal|merchant|catatan|tipe_bayar
OUT = pengeluaran, IN = pemasukan. Nominal dalam Rupiah.
Siklus periode keuangan: tanggal 25 sampai 24 bulan berikutnya.

DATA:
{data}

PERTANYAAN USER:
{pertanyaan}

Aturan menjawab:
- Bahasa Indonesia, ringkas, langsung ke inti.
- Hitung dari data di atas (jumlah, frekuensi, rata-rata, total) seakurat mungkin.
  Untuk mencocokkan hal seperti "kopi" atau "warnet", lihat kategori, merchant, dan catatan.
- Kalau diminta saran/analisa, beri yang praktis & spesifik berbasis pola data.
- Kalau data tidak cukup untuk menjawab, katakan apa adanya. Jangan mengarang transaksi."""
        resp = gemini_model.generate_content(prompt)
        jawab = (resp.text or "").strip() or "Maaf, aku tidak bisa menjawab itu."
        await update.message.reply_text(jawab[:4000])  # batas Telegram ~4096
    except Exception as e:
        logger.error(f"Gagal /tanya: {e}")
        await update.message.reply_text("❌ Gagal menganalisis. Coba lagi sebentar.")


# ==========================================
# /myid  &  /fitur
# ==========================================
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await update.message.reply_text(
        f"🆔 Telegram ID kamu: `{u.id}`\n"
        f"👤 Username: @{u.username or '-'}",
        parse_mode="Markdown",
    )


TEKS_FITUR = (
    "✨ *Fitur bot ini:*\n\n"
    "📝 *Catat pengeluaran*\n"
    "`/catat 50000 Makan nasi goreng`\n"
    "• Note pribadi pakai `;` → `/catat 50000 Makan ; ditalangin, tagih Andi`\n"
    "• Ketik *kemarin* untuk tanggal kemarin → `/catat 20000 Kopi kemarin`\n\n"
    "⚡ *Catat tanpa perintah*\n"
    "Ketik biasa seperti ngobrol, mis. \"jajan bakso 20rb di warung Ali\" — "
    "AI otomatis paham nominal, kategori, & barangnya.\n\n"
    "💵 *Catat pemasukan*\n"
    "`/masuk 5000000 Gaji`\n\n"
    "📸 *Foto struk otomatis*\n"
    "Kirim foto struk, dibaca sendiri (termasuk daftar barang).\n"
    "• *Caption* jadi catatan.\n"
    "• Caption berupa pertanyaan (mis. \"sudah pernah diupload?\") → bot cek duplikat dulu.\n\n"
    "📊 *Rekap transaksi*\n"
    "`/rekap hari ini` · `/rekap 1 agustus 2026` · `/rekap bulan ini`\n"
    "• Bisa disaring tipe bayar → \"rekap bulan ini paylater\"\n\n"
    "🤖 *Tanya AI* soal keuanganmu\n"
    "`/tanya berapa kali saya ngopi minggu ini`\n"
    "`/tanya beri saran biar lebih hemat`\n\n"
    "📈 *Dashboard web* — ringkasan, grafik, Total Pay Later per periode.\n"
    "Lihat spreadsheet & dashboard: `/info`\n\n"
    "💡 *Punya saran?* Kirim ke developer dengan `/saran`\n"
    "(boleh teks, atau foto beserta caption)."
)


async def fitur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TEKS_FITUR, parse_mode="Markdown")


# ==========================================
# /umumkan — broadcast ke semua user (khusus developer)
# ==========================================
async def umumkan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_ID or str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("⛔ Perintah ini khusus developer.")
        return

    # Ambil teks apa adanya (jangan pakai context.args -> baris baru hilang).
    bagian = (update.message.text or "").split(maxsplit=1)
    pesan = bagian[1].strip() if len(bagian) > 1 else ""
    if not pesan:
        await update.message.reply_text(
            "Tulis pesannya:\n`/umumkan Halo! Ada fitur baru: ...`",
            parse_mode="Markdown",
        )
        return

    uids = list(load_user_map(force=True).keys())
    await update.message.reply_text(f"📢 Mengirim ke {len(uids)} user...")

    teks = "📢 Info dari developer:\n\n" + pesan   # tanpa Markdown, biar tak gagal
    sukses = gagal = 0
    for uid in uids:
        try:
            await context.bot.send_message(chat_id=int(uid), text=teks)
            sukses += 1
        except Exception as e:
            gagal += 1
            logger.warning(f"broadcast gagal ke {uid}: {e}")
        await asyncio.sleep(0.05)   # jaga batas kirim Telegram

    await update.message.reply_text(f"✅ Terkirim: {sukses} | Gagal: {gagal}")


# ==========================================
# /saran — user kirim masukan ke developer
# ==========================================
menunggu_saran = set()   # user_id yang sedang diminta mengetik saran


async def _teruskan_saran(update, context, teks="", photo_id=None):
    if not ADMIN_ID:
        await update.message.reply_text("⚠️ Fitur saran belum aktif. Coba lagi nanti ya.")
        return
    u = update.effective_user
    header = f"💡 Saran dari @{u.username or '-'} (ID {u.id}):"
    try:
        if photo_id:
            cap = (header + "\n\n" + teks) if teks else header
            await context.bot.send_photo(
                chat_id=int(ADMIN_ID), photo=photo_id, caption=cap[:1024]
            )
        else:
            await context.bot.send_message(
                chat_id=int(ADMIN_ID), text=(header + "\n\n" + teks)[:4000]
            )
        await update.message.reply_text(
            "✅ Terima kasih! Saranmu sudah terkirim ke developer. 🙏"
        )
    except Exception as e:
        logger.error(f"Gagal kirim saran: {e}")
        await update.message.reply_text("❌ Gagal mengirim saran. Coba lagi sebentar.")


async def saran(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bagian = (update.message.text or "").split(maxsplit=1)
    teks = bagian[1].strip() if len(bagian) > 1 else ""

    if teks:
        menunggu_saran.discard(user_id)
        await _teruskan_saran(update, context, teks=teks)
    else:
        menunggu_saran.add(user_id)
        await update.message.reply_text(
            "💡 Silakan kirim saranmu — boleh *teks*, atau *foto beserta caption*.\n"
            "Ketik /batal untuk membatalkan.",
            parse_mode="Markdown",
        )


async def batal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in menunggu_saran:
        menunggu_saran.discard(update.effective_user.id)
        await update.message.reply_text("Dibatalkan. 👍")
    else:
        await update.message.reply_text("Tidak ada yang perlu dibatalkan.")


# ==========================================
# /statususer — cek aktivitas semua user (khusus developer)
# ==========================================
async def statususer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_ID or str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("⛔ Perintah ini khusus developer.")
        return

    await update.message.reply_text("📊 Mengecek aktivitas user...")
    try:
        records = get_users_sheet().get_all_records()
    except Exception as e:
        logger.error(f"statususer baca users: {e}")
        await update.message.reply_text("❌ Gagal membaca daftar user.")
        return

    hari_ini = now_wib().date()
    baris = []
    aktif = 0
    for rec in records:
        uname = rec.get("username") or "-"
        sid = rec.get("spreadsheet_id", "")
        jumlah = 0
        terakhir = None
        try:
            ss = get_client().open_by_key(sid)
            nilai = ss.worksheet(SHEET_PENGELUARAN).get_all_values()[1:]
            for r in nilai:
                if r and r[0]:
                    jumlah += 1
                    try:
                        d = datetime.strptime(str(r[0])[:10], "%Y-%m-%d").date()
                        if terakhir is None or d > terakhir:
                            terakhir = d
                    except ValueError:
                        pass
        except Exception:
            baris.append(f"⚠️ @{uname} — tak bisa dibaca (akses/sheet?)")
            continue

        if terakhir is None:
            baris.append(f"🔴 @{uname} — belum ada transaksi")
            continue

        selisih = (hari_ini - terakhir).days
        tgl = terakhir.strftime("%Y-%m-%d")
        if selisih <= 7:
            status = "🟢 aktif"
            aktif += 1
        elif selisih <= 30:
            status = "🟡 jarang"
        else:
            status = f"🔴 tidak aktif ({selisih} hr)"
        baris.append(f"{status} @{uname} — {jumlah} transaksi, terakhir {tgl}")

    kepala = f"📊 Status {len(records)} user ({aktif} aktif minggu ini):\n\n"
    await update.message.reply_text((kepala + "\n".join(baris))[:4000])


def main():
    cek_konfigurasi()
    load_user_map(force=True)
    logger.info(f"Jumlah user terdaftar: {len(_user_map or {})}")
    logger.info(f"Service account: {SERVICE_ACCOUNT_EMAIL}")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("daftar", daftar))
    app.add_handler(CommandHandler("buatkan", buatkan))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("catat", catat_manual))
    app.add_handler(CommandHandler("masuk", catat_masuk))
    app.add_handler(CommandHandler("hapus", hapus))
    app.add_handler(CommandHandler("dummy", dummy))
    app.add_handler(CommandHandler("hapusdummy", hapusdummy))
    app.add_handler(CommandHandler("tanya", tanya))
    app.add_handler(CommandHandler("rekap", rekap))
    app.add_handler(CommandHandler("fitur", fitur))
    app.add_handler(CommandHandler("saran", saran))
    app.add_handler(CommandHandler("batal", batal))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("umumkan", umumkan))
    app.add_handler(CommandHandler("statususer", statususer))
    app.add_handler(MessageHandler(filters.PHOTO, terima_foto))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, terima_teks))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_error_handler(error_handler)

    print("🤖 Bot multi-user sedang berjalan... Tekan CTRL+C untuk berhenti.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
