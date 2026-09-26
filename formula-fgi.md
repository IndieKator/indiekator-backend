# Cara Menghitung Fear and Greed Index IHSG

## Ringkasnya

Ada dua versi indeks. **V1** adalah sentiment lama di `/api/sentiment/*`.
**V2** adalah FGI mingguan di `/api/fgi`; versi ini menjadi sumber chart React.

> **Catatan:** draft lama menyebut empat keyword dan median. Implementasi V1
> yang berjalan sebenarnya hanya memakai keyword `ihsg`. V2 memakai tiga
> keyword dan rata-rata.

## Formula V1 - Sentiment Lama

V1 memakai Google Trends `ihsg`, lalu menormalisasikannya ke 0-100 pada data
yang sedang di-ingest. Harga hanya menentukan arah terhadap MA-125.

| Simbol | Arti sederhana |
| --- | --- |
| $GT_t$ | Nilai pencarian `ihsg` pada tanggal $t$ |
| $N_t$ | Nilai Trends setelah dinormalisasi ke 0-100 |
| $A_t$ | Arah harga: $1$ bila di atas MA-125, $-1$ bila di bawah atau sama dengan MA-125 |

$$
N_t = 100 \times \frac{GT_t - \min(GT)}{\max(GT) - \min(GT)}
$$

Jika semua nilai Trends sama, $N_t = 50$. Dengan $A_t = 1$ saat harga di atas
MA-125 dan $A_t = -1$ selain itu:

$$
FGI^{V1}_t = 50 + A_t \times \frac{N_t}{2}
$$

### Contoh aktual V1

**Diketahui** pada 1 September 2026:

$$
Close=6.599{,}943,\quad MA125=6.702{,}1175,\quad GT=1,\quad N=0
$$

Nilai $N=0$ berasal dari normalisasi seluruh data Trends pada satu kali ingest;
angka Google Trends mentah saja belum cukup untuk menghitungnya ulang tanpa
nilai minimum dan maksimum pada periode ingest tersebut.

**Langkah 1 - tentukan arah harga.** Karena harga lebih kecil daripada MA-125:

$$
6.599{,}943 < 6.702{,}1175 \Rightarrow A=-1
$$

**Langkah 2 - masukkan ke formula V1.**

$$
\begin{aligned}
FGI^{V1} &= 50+A\times\frac{N}{2} \\
&= 50+(-1)\times\frac{0}{2} \\
&= \mathbf{50{,}00}
\end{aligned}
$$

Hasilnya **Neutral**.

## Formula V2 - FGI

### Keyword dan pengambilan Google Trends

V2 mengambil tiga keyword secara **terpisah**. Setiap keyword memakai
`hl=id-ID`, `geo=ID`, dan periode tanggal yang sama.

| Variabel | Keyword |
| --- | --- |
| $K_1$ | `ihsg` |
| $K_2$ | `idx composite` |
| $K_3$ | `indeks harga saham gabungan` |

Google Trends memberi skala 0-100 untuk setiap query. Karena itu, setiap hasil
disimpan terlebih dahulu, kolom `isPartial` dibuang, tanggalnya disamakan, lalu
hanya minggu yang tersedia pada ketiga keyword yang dipakai. Nilai akhirnya
adalah rata-rata ketiganya, bukan satu keyword saja.

### Data range

Ingest meminta **18 bulan** data harga IHSG dan Google Trends. Harga harian
memerlukan periode lebih panjang agar MA-125 sudah tersedia; baru setelah itu
harga di-resample ke penutupan minggu terakhir (`W-SUN`). Google Trends untuk
periode yang sama menghasilkan seri mingguan yang kemudian digabungkan dengan
harga pada tanggal minggu yang cocok.

API tetap hanya mengembalikan **enam bulan terakhir**. Jadi, 18 bulan adalah
periode perhitungan dan pemanasan MA-125, bukan panjang chart yang ditampilkan.

### Variabel

Dengan $Close_t$ sebagai harga penutupan mingguan dan $MA125_t$ sebagai MA-125:

| Simbol | Arti sederhana |
| --- | --- |
| $t$ | Minggu yang sedang dihitung |
| $K_{1,t}$, $K_{2,t}$, $K_{3,t}$ | Nilai Google Trends dari masing-masing keyword pada minggu $t$ |
| $G_t$ | Rata-rata tiga nilai Google Trends |
| $D_t$ | Jarak harga dari MA-125 dalam persen; positif berarti harga di atas MA |
| $P_t$ | **Price Score** (0-100), yaitu kekuatan momentum harga |
| $S_t$ | **Search Score** (0-100), yaitu dampak minat pencarian terhadap arah pasar |
| $\operatorname{sign}(D_t)$ | $1$ bila harga di atas MA, $-1$ bila di bawah MA, dan $0$ bila tepat sama |
| $\operatorname{clip}(x,0,100)$ | Membatasi nilai $x$ agar tidak kurang dari 0 atau lebih dari 100 |

$$
G_t = \frac{K_{1,t}+K_{2,t}+K_{3,t}}{3}
\qquad
D_t = \frac{Close_t-MA125_t}{MA125_t} \times 100
$$

$$
P_t = \operatorname{clip}\left(50 + \frac{D_t}{6} \times 50, 0, 100\right)
$$

$$
S_t = \operatorname{clip}\left(50 + (G_t-50)\times\operatorname{sign}(D_t), 0, 100\right)
$$

$$
FGI^{V2}_t = 0{,}60 \times P_t + 0{,}40 \times S_t
$$

Bobot 60/40 membuat momentum harga menjadi sinyal utama, sementara pencarian
publik menjadi konfirmasi sentimen.

### Contoh aktual V2

**Diketahui** pada minggu 6 September 2026:

$$
Close=6.636{,}48,\quad MA125=6.662{,}47
$$

$$
K_1=15,\quad K_2=23,\quad K_3=46
$$

**Langkah 1 - hitung rata-rata minat pencarian.**

$$
G=\frac{15+23+46}{3}=\frac{84}{3}=28
$$

**Langkah 2 - hitung jarak harga dari MA-125.**

$$
\begin{aligned}
D &= \frac{6.636{,}48-6.662{,}47}{6.662{,}47}\times100 \\
&= -0{,}39\%
\end{aligned}
$$

**Langkah 3 - hitung Price Score.**

$$
\begin{aligned}
P &= 50+\frac{-0{,}39}{6}\times50 \\
&= 50-3{,}25 \\
&= 46{,}75
\end{aligned}
$$

**Langkah 4 - hitung Search Score.** Harga berada di bawah MA-125, jadi
$\operatorname{sign}(D)=-1$.

$$
\begin{aligned}
S &= 50+(28-50)\times(-1) \\
&= 50+22 \\
&= 72
\end{aligned}
$$

**Langkah 5 - gabungkan kedua skor.**

$$
\begin{aligned}
FGI^{V2} &= 0{,}60(46{,}75)+0{,}40(72) \\
&= \mathbf{56{,}85}
\end{aligned}
$$

Hasilnya **Greed**. Batas zona: Extreme Fear $\le25$, Fear $\le45$,
Neutral $\le55$, Greed $\le75$, lalu Extreme Greed.

### Menelusuri hasil

Setiap snapshot V2 disimpan per minggu di `fgi_snapshots`. Untuk memeriksa
perhitungan, cocokkan `close_price` dan `ma_125` dengan $D_t$; tiga kolom
`trend_*` dengan $G_t$; lalu periksa `price_score`, `search_score`, dan `fgi`.
Dengan urutan itu, nilai akhir dapat dihitung ulang dari input mentahnya.
