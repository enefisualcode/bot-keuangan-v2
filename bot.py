<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Keuangan — Hari Ini</title>

<!-- Buka seperti aplikasi saat ditambahkan ke Home Screen (iPhone) -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<meta name="apple-mobile-web-app-title" content="Keuangan">
<meta name="mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#0B1220">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" href="apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&family=Instrument+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">

<style>
:root{
  --ink:#0B1220; --surface:#131D30; --surface-2:#1C2841; --line:#293752;
  --blue:#54A8FF; --orange:#FF9A3D; --orange-deep:#FF7847;
  --text:#E9F0FA; --muted:#8C9CB8; --faint:#5A6B88;
  --display:"Bricolage Grotesque",system-ui,sans-serif;
  --body:"Instrument Sans",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  background:var(--ink);color:var(--text);font-family:var(--body);
  -webkit-font-smoothing:antialiased;padding:0 0 48px;max-width:560px;margin:0 auto;
}

.top{padding:28px 20px 0;display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.eyebrow{font-family:var(--mono);font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint)}
.periode{font-family:var(--mono);font-size:11.5px;color:var(--muted)}

/* ---------- hero: hari ini ---------- */
.hero{
  margin:16px 20px 0;background:var(--surface);border:1px solid var(--line);
  border-radius:20px;padding:22px 22px 20px;
}
.hero-lbl{
  font-family:var(--mono);font-size:10px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--faint);
}
.hero-tgl{font-size:12.5px;color:var(--muted);margin-top:3px}
.hero-num{
  font-family:var(--display);font-size:42px;font-weight:800;
  letter-spacing:-.03em;line-height:1.05;margin-top:12px;
  font-variant-numeric:tabular-nums;
}
.banding{
  display:flex;align-items:center;gap:8px;margin-top:12px;
  font-size:12.5px;color:var(--muted);line-height:1.45;
}
.pil{
  font-family:var(--mono);font-size:11px;font-weight:500;
  padding:3px 8px;border-radius:99px;white-space:nowrap;
}
.pil.atas{background:rgba(255,120,71,.15);color:var(--orange-deep)}
.pil.bawah{background:rgba(84,168,255,.15);color:var(--blue)}

/* baris total Pay Later di kartu hero — pengingat menahan diri */
.hero-pl{
  display:flex;align-items:baseline;justify-content:space-between;gap:12px;
  margin-top:14px;padding-top:13px;border-top:1px solid var(--line);
}
.hero-pl:empty{display:none}
.hero-pl .pl-lbl{
  font-family:var(--mono);font-size:10px;letter-spacing:.13em;
  text-transform:uppercase;color:var(--faint);
}
.hero-pl .pl-val{
  font-family:var(--mono);font-size:15px;font-weight:600;letter-spacing:-.01em;
  font-variant-numeric:tabular-nums;color:var(--muted);
}
.hero-pl.ada .pl-val{color:var(--orange-deep)}

/* ---------- statistik ---------- */
.stat{margin:12px 20px 0;display:grid;grid-template-columns:1fr 1fr;gap:10px}
.kartu{
  background:var(--surface);border:1px solid var(--line);
  border-radius:14px;padding:14px 15px;
}
.kartu .l{
  font-family:var(--mono);font-size:9.5px;letter-spacing:.13em;
  text-transform:uppercase;color:var(--faint);
}
.kartu .v{
  font-family:var(--mono);font-size:17px;font-weight:500;margin-top:6px;
  font-variant-numeric:tabular-nums;letter-spacing:-.01em;
}
.kartu .s{font-size:11px;color:var(--muted);margin-top:3px}

h2{
  font-family:var(--mono);font-size:10.5px;font-weight:500;
  letter-spacing:.16em;text-transform:uppercase;color:var(--faint);
  margin:32px 20px 12px;display:flex;align-items:center;gap:10px;
}
h2::after{content:"";flex:1;height:1px;background:var(--line)}

/* ---------- transaksi hari ini ---------- */
.trx{margin:0 20px}
.trx-row{
  display:grid;grid-template-columns:auto 1fr auto;gap:12px;
  align-items:center;padding:12px 0;border-bottom:1px solid var(--line);
}
.trx-row:last-child{border-bottom:none}
.trx-row.sisa{display:none}
.trx.trx-buka .trx-row.sisa{display:grid}
.trx-toggle{
  display:block;width:100%;margin-top:2px;padding:12px 0 2px;
  background:none;border:none;cursor:pointer;text-align:center;
  font-family:var(--mono);font-size:11px;letter-spacing:.05em;color:var(--blue);
}
.trx-toggle:hover{color:var(--text)}
.tanda{
  width:34px;height:34px;border-radius:10px;background:var(--surface-2);
  display:flex;align-items:center;justify-content:center;
  font-family:var(--mono);font-size:11px;font-weight:600;color:var(--blue);
}
.trx-nama{font-size:14px;line-height:1.3}
.trx-meta{font-size:11.5px;color:var(--faint);margin-top:2px}
.trx-nilai{
  font-family:var(--mono);font-size:14px;font-weight:500;
  font-variant-numeric:tabular-nums;
}
.kosong{
  margin:0 20px;background:var(--surface);border:1px dashed var(--line);
  border-radius:14px;padding:22px;text-align:center;
  font-size:13px;color:var(--muted);line-height:1.5;
}

/* ---------- grafik harian ---------- */
.harian{
  margin:0 20px;background:var(--surface);border:1px solid var(--line);
  border-radius:16px;padding:18px 16px 12px;
}
.chart{display:flex;align-items:flex-end;gap:3px;height:120px;position:relative}
.col{flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%;cursor:pointer}
.col i{display:block;width:100%;background:var(--orange);border-radius:3px 3px 1px 1px;min-height:2px;opacity:.78}
.col.hi i{opacity:1;background:var(--orange-deep)}
.col.kini i{opacity:1;background:var(--blue)}
.garis{position:relative;height:0}
.garis::before{
  content:"";position:absolute;left:0;right:0;top:0;
  border-top:1px dashed var(--faint);opacity:.45;
}
.xlab{display:flex;justify-content:space-between;font-family:var(--mono);font-size:9.5px;color:var(--faint);margin-top:9px}
.catatan{font-size:12px;color:var(--muted);margin:11px 2px 0;line-height:1.5}
.catatan b{color:var(--text);font-weight:600}

/* ---------- pemilih hari (rincian) ---------- */
.rincian-head{display:flex;align-items:center;gap:10px;margin:32px 20px 12px}
.rincian-head h2{margin:0}
.rincian-head h2::after{display:none}
.rincian-head .rule{flex:1;height:1px;background:var(--line)}
#pilihHari{
  flex:none;max-width:56%;
  font-family:var(--mono);font-size:11px;color:var(--blue);
  background:var(--surface-2);border:1px solid var(--line);border-radius:9px;
  padding:7px 26px 7px 11px;cursor:pointer;-webkit-appearance:none;appearance:none;
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2 3.5 L5 6.5 L8 3.5' stroke='%2354A8FF' fill='none' stroke-width='1.4' stroke-linecap='round' stroke-linejoin='round'/></svg>");
  background-repeat:no-repeat;background-position:right 10px center;
}

/* ---------- batang terpilih + tooltip ---------- */
.col.pilih i{opacity:1;outline:2px solid rgba(233,240,250,.9);outline-offset:1px;border-radius:3px}
.chart-tip{
  position:absolute;transform:translateX(-50%);pointer-events:none;white-space:nowrap;
  background:var(--surface-2);border:1px solid var(--line);border-radius:9px;
  padding:5px 10px;box-shadow:0 8px 20px rgba(0,0,0,.4);
  opacity:0;transition:opacity .15s;z-index:5;
}
.chart-tip.tampil{opacity:1}
.chart-tip .tip-tgl{
  display:block;font-family:var(--mono);font-size:9px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--faint);margin-bottom:1px;
}
.chart-tip .tip-val{font-family:var(--mono);font-size:12px;font-weight:600;color:var(--blue)}

/* ---------- kategori ---------- */
.kat{margin:0 20px;display:flex;flex-direction:column}
.kat-row{
  display:grid;grid-template-columns:1fr auto;gap:4px 12px;
  padding:11px 0;border-bottom:1px solid var(--line);align-items:center;
}
.kat-row:last-child{border-bottom:none}
.kat-nama{font-size:14px}
.kat-nilai{font-family:var(--mono);font-size:13.5px;font-variant-numeric:tabular-nums}
.kat-bar{grid-column:1/-1;height:4px;background:var(--surface-2);border-radius:99px;overflow:hidden}
.kat-bar span{display:block;height:100%;background:var(--blue);border-radius:99px;opacity:.7}
.kat-row:first-child .kat-bar span{opacity:1}
.kat-pct{font-family:var(--mono);font-size:10.5px;color:var(--faint)}

.kaki{
  margin:34px 20px 0;padding-top:16px;border-top:1px solid var(--line);
  font-family:var(--mono);font-size:10.5px;color:var(--faint);line-height:1.7;
}

@media (prefers-reduced-motion:no-preference){
  .hero,.stat,.trx,.kosong,.harian,.kat{animation:naik .5s cubic-bezier(.22,.9,.3,1) backwards}
  .stat{animation-delay:.06s}
  .trx,.kosong{animation-delay:.12s}
  .harian{animation-delay:.18s}
  .kat{animation-delay:.24s}
  @keyframes naik{from{opacity:0;transform:translateY(10px)}}
}
</style>

<div class="top">
  <div class="eyebrow">Pengeluaran</div>
  <div class="periode" id="periode">—</div>
</div>

<section class="hero">
  <div class="hero-lbl" id="heroLbl">Hari ini</div>
  <div class="hero-tgl" id="heroTgl">—</div>
  <div class="hero-num" id="heroNum">—</div>
  <div class="banding" id="banding"></div>
  <div class="hero-pl" id="heroPL"></div>
</section>

<div class="stat">
  <div class="kartu">
    <div class="l">Rata-rata harian</div>
    <div class="v" id="vRata">—</div>
    <div class="s" id="sRata">—</div>
  </div>
  <div class="kartu">
    <div class="l">Total periode</div>
    <div class="v" id="vTotal">—</div>
    <div class="s" id="sTotal">—</div>
  </div>
</div>

<div class="rincian-head">
  <h2 id="rincianJudul">Rincian hari ini</h2>
  <span class="rule"></span>
  <select id="pilihHari" aria-label="Pilih hari"></select>
</div>
<div id="wadahTrx"></div>

<h2>Grafik harian</h2>
<div class="harian">
  <div class="chart" id="chart"></div>
  <div class="xlab"><span id="xAwal">—</span><span id="xAkhir">—</span></div>
  <div class="catatan" id="catatan">—</div>
</div>

<!-- Disembunyikan sementara: kategori belum valid.
     Aktifkan lagi dengan menghapus tanda komentar di baris berikut. -->
<!--
<h2>Ke mana perginya</h2>
<div class="kat" id="kat"></div>
-->

<div class="kaki" id="kaki">—</div>

<script>
/* ============================================================
   SUMBER DATA
   Tempel URL Apps Script kamu di bawah ini.
   Bentuknya: https://script.google.com/macros/s/AKfyc..../exec
   Cara membuatnya ada di README dan file apps-script.gs.
   ============================================================ */
const URL_DATA = "https://script.google.com/macros/s/AKfycbzjtMJfycmp0vPscid3hxf0KAFzQ7nPG0_hzbP8RH60LmKx_bCC9I5MlAaoHrqeeFhI/exec";
const HARI_SIKLUS = 25;

let pengeluaran = [];
let totalPaylaterSheet = null;   // diisi dari Rekap Daily (via Apps Script) kalau tersedia
let hariDipilih = null;          // kunci tanggal yang sedang dilihat di Rincian; null = hari ini

/* ---------- util ---------- */
const rp  = n => "Rp" + Math.round(n).toLocaleString("id-ID");
const rpk = n => n >= 1e6 ? "Rp" + (n/1e6).toFixed(n%1e6===0?0:1) + " jt"
                          : "Rp" + Math.round(n/1000) + "rb";
const d = s => new Date(s + "T00:00:00");
const fmt = (t,o) => t.toLocaleDateString("id-ID", o);
const kunciTgl = t => t.getFullYear() + "-" +
  String(t.getMonth()+1).padStart(2,"0") + "-" +
  String(t.getDate()).padStart(2,"0");

function awalPeriode(acuan){
  const t = new Date(acuan);
  const m = t.getDate() >= HARI_SIKLUS ? t.getMonth() : t.getMonth()-1;
  return new Date(t.getFullYear(), m, HARI_SIKLUS);
}

function gambar(){
  if (!pengeluaran.length){
    document.getElementById("wadahTrx").innerHTML =
      `<div class="kosong">Belum ada data pengeluaran.<br>
       Catat lewat bot untuk mulai mengisinya.</div>`;
    document.getElementById("kaki").textContent = "Tidak ada data";
    return;
  }

  const sekarang = new Date();
  const hariIni = new Date(sekarang.getFullYear(), sekarang.getMonth(), sekarang.getDate());
  const kunciHariIni = kunciTgl(hariIni);

  const mulai   = awalPeriode(hariIni);
  const selesai = new Date(mulai.getFullYear(), mulai.getMonth()+1, HARI_SIKLUS-1);
  const totalHari = Math.round((selesai-mulai)/864e5)+1;
  const hariKe    = Math.max(Math.round((hariIni-mulai)/864e5)+1, 1);

  const periodeIni = pengeluaran.filter(r=>{const t=d(r[0]); return t>=mulai && t<=selesai;});
  const trxHariIni = periodeIni.filter(r=>r[0]===kunciHariIni);

  const totalPeriode = periodeIni.reduce((a,r)=>a+r[2],0);
  const totalHariIni = trxHariIni.reduce((a,r)=>a+r[2],0);

  /* rata-rata dihitung dari hari yang benar-benar ada transaksinya */
  const hariAktif = new Set(periodeIni.map(r=>r[0])).size;
  const rata = hariAktif ? totalPeriode/hariAktif : 0;

  /* ---------- header ---------- */
  document.getElementById("periode").textContent =
    fmt(mulai,{day:"numeric",month:"short"}) + " – " +
    fmt(selesai,{day:"numeric",month:"short",year:"numeric"});

  /* ---------- hero ----------
     Kartu atas sekarang mengikuti hari yang dipilih di dropdown/grafik.
     Pengisiannya dilakukan oleh renderHero(), dipanggil dari pilihHari(). */

  /* ---------- total Pay Later (pengingat menahan diri) ----------
     Utamakan nilai "Total Paylater" dari sheet Rekap Daily (dikirim Apps Script
     sebagai json.totalPaylater). Kalau field itu belum tersedia, jatuh kembali
     ke hitungan lama: menjumlah transaksi ber-Tipe Bayar "Pay Later" periode ini. */
  const totalPayLater = (totalPaylaterSheet != null)
    ? totalPaylaterSheet
    : periodeIni.filter(r => r[6] === "Pay Later").reduce((a,r) => a + r[2], 0);
  const elPL = document.getElementById("heroPL");
  elPL.className = "hero-pl" + (totalPayLater > 0 ? " ada" : "");
  elPL.innerHTML =
    `<span class="pl-lbl">Total Pay Later</span>
     <span class="pl-val">${rp(totalPayLater)}</span>`;

  /* ---------- statistik ---------- */
  document.getElementById("vRata").textContent = rp(rata);
  document.getElementById("sRata").textContent = `dari ${hariAktif} hari ada transaksi`;
  document.getElementById("vTotal").textContent = rpk(totalPeriode);
  document.getElementById("sTotal").textContent = `hari ke-${hariKe} dari ${totalHari}`;

  /* ---------- rincian per hari + grafik interaktif ----------
     Pilih hari lewat dropdown ATAU ketuk batang grafik — keduanya menampilkan
     total pengeluaran + rincian transaksi hari itu. Transaksi diurutkan dari
     yang terakhir dicatat ke paling lama; tampil 5 teratas, sisanya lewat tombol. */
  const BATAS = 5;

  // kumpulkan transaksi & total per hari (dalam periode)
  const trxPerHari = new Map();
  const perHari = new Map();
  periodeIni.forEach(r=>{
    if(!trxPerHari.has(r[0])) trxPerHari.set(r[0], []);
    trxPerHari.get(r[0]).push(r);
    perHari.set(r[0], (perHari.get(r[0])||0) + r[2]);
  });

  const buatBaris = r => {
    const [,kat,nom,merchant,sumber,catatan,tipe] = r;
    const judul = merchant && merchant !== "-" ? merchant : kat;
    const bagian = [kat];
    if (catatan) bagian.push(catatan);
    if (tipe === "Pay Later") bagian.push("Pay Later");
    const row = document.createElement("div");
    row.className = "trx-row";
    row.innerHTML = `
      <span class="tanda">${kat.slice(0,2).toUpperCase()}</span>
      <span>
        <div class="trx-nama">${judul}</div>
        <div class="trx-meta">${bagian.join(" · ")}</div>
      </span>
      <span class="trx-nilai">${rp(nom)}</span>`;
    return row;
  };

  function renderRincian(kunci){
    const wadah = document.getElementById("wadahTrx");
    wadah.innerHTML = "";
    document.getElementById("rincianJudul").textContent =
      (kunci === kunciHariIni)
        ? "Rincian hari ini"
        : "Rincian " + fmt(d(kunci),{weekday:"long",day:"numeric",month:"long"});

    const trx = trxPerHari.get(kunci) || [];
    if (!trx.length){
      wadah.innerHTML = (kunci === kunciHariIni)
        ? `<div class="kosong">Belum ada catatan hari ini.<br>
             Kirim struk atau <b>/catat</b> lewat bot untuk mengisinya.</div>`
        : `<div class="kosong">Tidak ada transaksi pada hari ini.</div>`;
      return;
    }
    const urut = trx.slice().reverse();   // terbaru di atas
    const list = document.createElement("div");
    list.className = "trx";
    urut.forEach((r,i)=>{
      const row = buatBaris(r);
      if (i >= BATAS) row.classList.add("sisa");
      list.appendChild(row);
    });
    if (urut.length > BATAS){
      const sisa = urut.length - BATAS;
      const tombol = document.createElement("button");
      tombol.className = "trx-toggle";
      tombol.setAttribute("aria-expanded","false");
      const labelTutup = `Lihat semua ${urut.length} transaksi (${sisa} lagi) ▾`;
      const labelBuka  = `Tampilkan lebih sedikit ▴`;
      tombol.textContent = labelTutup;
      tombol.addEventListener("click", ()=>{
        const buka = list.classList.toggle("trx-buka");
        tombol.textContent = buka ? labelBuka : labelTutup;
        tombol.setAttribute("aria-expanded", buka ? "true" : "false");
      });
      list.appendChild(tombol);
    }
    wadah.appendChild(list);
  }

  /* ---------- grafik harian (interaktif) ---------- */
  const deret=[];
  for(let i=0;i<hariKe;i++){
    const t=new Date(mulai.getFullYear(),mulai.getMonth(),mulai.getDate()+i);
    const k=kunciTgl(t);
    deret.push({tgl:t,k:k,nilai:perHari.get(k)||0,kini:k===kunciHariIni});
  }
  const puncak = Math.max(...deret.map(x=>x.nilai),1);
  const chart = document.getElementById("chart");
  chart.innerHTML = "";

  const tip = document.createElement("div");
  tip.className = "chart-tip";
  tip.innerHTML = `<span class="tip-tgl"></span><span class="tip-val"></span>`;
  chart.appendChild(tip);

  const kolomByKunci = new Map();
  deret.forEach((x,i)=>{
    const col=document.createElement("div");
    col.className="col" + (x.kini?" kini":(x.nilai===puncak?" hi":""));
    const bar=document.createElement("i");
    bar.style.height="0%";
    bar.style.transition="height .55s cubic-bezier(.22,.9,.3,1) "+(i*26)+"ms";
    col.appendChild(bar);
    col.addEventListener("click", ()=>{ hariDipilih = x.k; pilihHari(x.k, true); });
    chart.appendChild(col);
    kolomByKunci.set(x.k, col);
    requestAnimationFrame(()=>bar.style.height=Math.max(x.nilai/puncak*100,1.5)+"%");
  });

  function tampilkanTip(kunci){
    const info = deret.find(x=>x.k===kunci);
    const col = kolomByKunci.get(kunci);
    if (!info || !col){ tip.classList.remove("tampil"); return; }
    const total = perHari.get(kunci) || 0;
    tip.querySelector(".tip-tgl").textContent = fmt(info.tgl,{day:"numeric",month:"short"});
    tip.querySelector(".tip-val").textContent = rp(total);
    tip.classList.add("tampil");
    requestAnimationFrame(()=>{
      const H = chart.clientHeight;
      const barPx = Math.max(total/puncak, 0.015) * H;
      const th = tip.offsetHeight;
      let bottom = barPx + 8;
      if (bottom + th > H - 2) bottom = H - th - 2;   // jangan keluar dari atas grafik
      tip.style.bottom = bottom + "px";
      const center = col.offsetLeft + col.offsetWidth/2;
      const half = tip.offsetWidth/2;
      tip.style.left = Math.min(Math.max(center, half), chart.clientWidth - half) + "px";
    });
  }

  const sel = document.getElementById("pilihHari");

  /* Isi kartu atas (tanggal, total besar, banding) untuk satu hari.
     Total Pay Later TIDAK diubah di sini — itu angka seluruh periode, bukan per hari. */
  function renderHero(kunci){
    const totalHari = perHari.get(kunci) || 0;
    const iniHariIni = (kunci === kunciHariIni);

    document.getElementById("heroLbl").textContent = iniHariIni ? "Hari ini" : "Hari dipilih";
    document.getElementById("heroTgl").textContent =
      fmt(d(kunci),{weekday:"long",day:"numeric",month:"long",year:"numeric"});
    document.getElementById("heroNum").textContent = rp(totalHari);

    const selisih = totalHari - rata;
    const pct = rata ? Math.abs(selisih/rata*100) : 0;
    document.getElementById("banding").innerHTML = totalHari === 0
      ? (iniHariIni ? `Belum ada pengeluaran hari ini.`
                    : `Tidak ada pengeluaran di tanggal ini.`)
      : `<span class="pil ${selisih>0?"atas":"bawah"}">
           ${selisih>0?"▲":"▼"} ${pct.toFixed(0)}%
         </span>
         <span>${selisih>0?"di atas":"di bawah"} rata-rata harianmu</span>`;
  }

  function pilihHari(kunci, withTip){
    if (sel.value !== kunci) sel.value = kunci;
    renderHero(kunci);
    renderRincian(kunci);
    chart.querySelectorAll(".col.pilih").forEach(c=>c.classList.remove("pilih"));
    if (withTip){
      const col = kolomByKunci.get(kunci);
      if (col) col.classList.add("pilih");
      tampilkanTip(kunci);
    } else {
      tip.classList.remove("tampil");
    }
  }

  // isi dropdown: semua hari dari awal periode s/d hari ini (terbaru dulu),
  // supaya setiap batang grafik punya opsi dropdown yang cocok persis.
  const daftarHari = deret.map(x=>x.k).slice().reverse();
  if (hariDipilih == null || !daftarHari.includes(hariDipilih)) hariDipilih = kunciHariIni;
  sel.innerHTML = "";
  daftarHari.forEach(k=>{
    const opt = document.createElement("option");
    opt.value = k;
    opt.textContent = (k===kunciHariIni ? "Hari ini · " : "") +
      fmt(d(k),{weekday:"short",day:"numeric",month:"short"});
    if (k===hariDipilih) opt.selected = true;
    sel.appendChild(opt);
  });
  sel.onchange = () => { hariDipilih = sel.value; pilihHari(hariDipilih, true); };

  // tampilkan hari terpilih. Default hari ini = tanpa tooltip (tampilan bersih);
  // kalau sebelumnya sedang melihat hari lain, pertahankan sorotan + tooltip.
  pilihHari(hariDipilih, hariDipilih !== kunciHariIni);

  document.getElementById("xAwal").textContent  = fmt(mulai,{day:"numeric",month:"short"});
  document.getElementById("xAkhir").textContent = fmt(hariIni,{day:"numeric",month:"short"});

  const terboros = deret.find(x=>x.nilai===puncak);
  document.getElementById("catatan").innerHTML =
    `Ketuk batang untuk lihat total &amp; rincian hari itu. Paling boros
     <b>${fmt(terboros.tgl,{weekday:"long",day:"numeric",month:"long"})}</b> — ${rp(puncak)}.`;

  /* ---------- kategori (disembunyikan sementara — kategori belum valid) ----------
     Blok ini otomatis dilewati selama elemen #kat masih di-comment di HTML.
     Begitu HTML-nya diaktifkan lagi, bagian ini langsung jalan tanpa perubahan. */
  const elKat=document.getElementById("kat");
  if (elKat){
    elKat.innerHTML = "";   // kosongkan dulu supaya tidak dobel saat disegarkan ulang
    const perKat=new Map();
    periodeIni.forEach(r=>perKat.set(r[1],(perKat.get(r[1])||0)+r[2]));
    [...perKat.entries()].sort((a,b)=>b[1]-a[1]).forEach(([nama,nilai],i)=>{
      const p=nilai/totalPeriode*100;
      const row=document.createElement("div");
      row.className="kat-row";
      row.innerHTML=`
        <span class="kat-nama">${nama}</span>
        <span class="kat-nilai">${rp(nilai)}</span>
        <span class="kat-bar"><span style="width:0"></span></span>
        <span class="kat-pct">${p.toFixed(0)}%</span>`;
      elKat.appendChild(row);
      const isi=row.querySelector(".kat-bar span");
      isi.style.transition="width .7s cubic-bezier(.22,.9,.3,1) "+(i*70+150)+"ms";
      requestAnimationFrame(()=>isi.style.width=p+"%");
    });
  }

  /* ---------- kaki ---------- */
  document.getElementById("kaki").innerHTML =
    `${trxHariIni.length} transaksi hari ini · ${periodeIni.length} periode ini<br>
     Siklus tanggal ${HARI_SIKLUS} ke ${HARI_SIKLUS-1} ·
     <span id="segar">memuat…</span>`;

}

/* ---------- ambil data ---------- */
function tampilkanGagal(pesan){
  document.getElementById("heroNum").textContent = "—";
  document.getElementById("wadahTrx").innerHTML =
    `<div class="kosong">${pesan}</div>`;
  document.getElementById("kaki").textContent = "Gagal memuat";
}

/* Data diambil lewat JSONP, bukan fetch.
   Alasannya: browser memblokir fetch dari file:// ke internet,
   sedangkan <script> tidak kena batasan itu. Jadi cara ini tetap
   jalan baik file dibuka langsung dari komputer maupun dari web. */
let sedangMuat = false;

function muat(){
  if (URL_DATA.indexOf("script.google.com") === -1){
    tampilkanGagal("URL Apps Script belum diisi.<br>" +
      "Buka <b>index.html</b>, cari <b>URL_DATA</b> di bagian atas script, " +
      "lalu tempel URL milikmu.");
    return;
  }
  if (sedangMuat) return;
  sedangMuat = true;

  const nama = "terimaData" + Date.now();
  const s = document.createElement("script");
  const batas = setTimeout(() => {
    gagal("Server tidak menjawab.<br>Coba muat ulang halaman.");
  }, 20000);

  function bersihkan(){
    clearTimeout(batas);
    delete window[nama];
    if (s.parentNode) s.parentNode.removeChild(s);
    sedangMuat = false;
  }
  function gagal(pesan){
    bersihkan();
    tampilkanGagal(pesan);
  }

  window[nama] = (json) => {
    bersihkan();
    pengeluaran = (json && json.pengeluaran) || [];
    totalPaylaterSheet = (json && json.totalPaylater != null && !isNaN(Number(json.totalPaylater)))
      ? Number(json.totalPaylater) : null;
    gambar();
    const el = document.getElementById("segar");
    if (el) el.textContent = "Diperbarui " +
      new Date().toLocaleTimeString("id-ID", {hour:"2-digit", minute:"2-digit"});
  };

  s.src = URL_DATA + "?callback=" + nama + "&_=" + Date.now();
  s.onerror = () => gagal("Tidak bisa menghubungi server.<br>Cek koneksi internet, lalu muat ulang halaman.");
  document.body.appendChild(s);
}

muat();
/* Setiap dashboard dibuka/kembali ke depan: segarkan data & kembali ke Hari Ini.
   Selama masih dibuka, pilihan hari tetap (tidak tersentak balik). */
document.addEventListener("visibilitychange", () => {
  if (!document.hidden){
    hariDipilih = null;   // kembali ke hari ini saat dashboard dibuka lagi
    muat();
  }
});
</script>
