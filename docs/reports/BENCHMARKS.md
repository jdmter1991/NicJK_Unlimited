# BENCHMARKS — `swtor_korriban`, dedicated server, `sv_fps 40`

Method: `tools\run_bench.ps1` starts `taystjkded.x86_64.exe` from an isolated dev directory
(`+set fs_basepath <original GameData> +set fs_homepath <dev dir>`), loads the map, adds N bots at skill 5,
waits for the warm-up, then samples process CPU once per second for the window. "ms/frame" = CPU seconds /
wall seconds / 40. `SVPROF` rows come from the in-engine `sv_profile` cvar (wall-clock time of work inside
`SV_Frame`). No human clients. Machine: the user's PC; game assets on the E: HDD.

Raw rows are in `devgame_baseline\bench_results.jsonl` and `devgame_dev\bench_results.jsonl`;
console logs are the `bench_*.stderr.log` / `bench_*.qconsole.log` files next to them.

## A. Original fork (commit `1ef7a9f1f`, unmodified)

| Bots | CPU % of one core | ms/frame | Worst 1 s | Peak working set |
|---:|---:|---:|---:|---:|
| 0 | 0.4 | 0.10 | 4.6 % | 1,606 MB |
| 5 | 62.5 | 15.63 | 98.9 % | 1,607 MB |
| 10 | 85.5 | 21.38 | 100 % | 1,607 MB |
| 15 | 99.0 | 24.75 | 100 % | 1,607 MB |
| 20, 26 | not measured | | | |

## B. Development build, accelerator off vs on (same binary, `cm_accel` 0 / 1)

| Run | Bots | CPU % | ms/frame (CPU) | Notes |
|---|---:|---:|---:|---|
| `cm_accel 0` | 10 | 84.6 | 21.15 | equals the original within noise |
| `cm_accelVerify 1` | 10 | 80.7 | 20.17 | both paths per trace; 500,000 traces, 0 mismatches; 84 µs vs 3.2 µs |
| `cm_accel 1` | 10 | 13.0 | 3.25 | |
| `cm_accel 1` | 20 | 22.4 | 5.60 | |
| `cm_accel 1` | 26 | 25.5 | 6.37 | 60 s window |
| `cm_accel 1` | 26 | 26.7 | 6.68 | 120 s window, console output on SSD |

Peak working set with the accelerator: 1,680 MB (+~75 MB, of which 36 MB is the hierarchy).

## C. In-engine profile, 26 bots, accelerator on, console output on SSD (4 consecutive 30 s windows)

| Window | Frames | Over 25 ms | Total avg (max) ms | Bot AI avg (max) | Game avg (max) | Snapshots avg (max) |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 1,200 | 1 | 6.37 (27.6) | 2.71 (21.8) | 2.89 (21.9) | 0.77 (2.6) |
| 2 | 1,201 | 6 | 6.77 (29.9) | 3.02 (24.1) | 2.97 (21.7) | 0.78 (3.6) |
| 3 | 1,201 | 2 | 6.64 (26.9) | 2.88 (22.1) | 2.99 (21.1) | 0.77 (2.3) |
| 4 | 1,201 | 4 | 6.47 (29.6) | 2.74 (22.7) | 2.96 (22.9) | 0.76 (2.4) |

Per frame at 26 bots: 286 bot-AI traces (7.1 µs each, 2.0 ms), 371 game traces (2.8 µs each, 1.0 ms),
52 point-contents (0.14 ms).

## D. In-engine profile, 10 bots, stock collision path (`cm_accel 0`) for comparison

Total 20.0 – 23.5 ms/frame (max 104 ms); bot AI 7.5 – 7.8 ms; game 12.3 – 15.5 ms; 105 – 128 µs per bot
trace, 52 – 59 µs per game trace, ~250 µs per point-contents; ~1 million leaf-brush records walked per frame.

## E. After the AI changes (commit 733952165), 26 bots, 4 consecutive 30 s windows

Bots now think on every server frame (31,200 thinks per window instead of ~24,950).

| Window | Over 25 ms | Total avg (max) ms | Bot AI avg (max) | Game avg (max) | Thinks | Think avg | AI traces per think |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3 | 5.58 (484, includes bot join) | 1.66 (25.8) | 3.16 (482) | 30,576 | 62 us | 8.3 |
| 2 | 0 | 5.25 (24.4) | 1.69 (19.3) | 2.80 (21.4) | 31,200 | 64 us | 7.9 |
| 3 | 1 | 5.57 (31.1) | 1.85 (28.0) | 2.96 (22.7) | 31,200 | 70 us | 8.2 |
| 4 | 0 | 5.56 (24.1) | 1.86 (20.1) | 2.96 (20.7) | 31,200 | 71 us | 8.3 |

Process CPU over the 125 s window: 24.1 % of one core (6.0 ms per frame). 89 kills logged.
Before the AI changes (same engine): bot AI 2.98 - 3.05 ms per frame at 143 - 146 us per think, 13.4 - 13.8 traces per think.

## Limits of these numbers

* Bot behaviour is not deterministic, so rows are not the same workload trace-for-trace
  (only the `cm_accelVerify` row compares identical traces).
* Longest run so far is 2 minutes.
* Early runs had 0.3 – 1.6 s stalls caused by console output being redirected to the HDD (see
  `PERFORMANCE_DIAGNOSIS.md` §3); rows marked "console output on SSD" are free of that artifact, earlier
  rows' averages include it.
* No client, renderer, or network measurements yet.
