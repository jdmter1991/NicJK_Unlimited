# Capture the game's own window (title bar included) every time the game writes a new screenshot file.
#   capture_window.ps1 -Process nicjk.x86_64 -Watch <screenshots dir> -Out <dir> -Names a,b,c,d
# Only the rectangle of that window is copied from the screen, nothing else on the desktop.
param([string]$Process = "nicjk.x86_64", [string]$Watch, [string]$Out, [string[]]$Names, [int]$TimeoutSec = 900)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class NabooWin {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int a, out RECT r, int s);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[void][NabooWin]::SetProcessDPIAware()
New-Item -ItemType Directory -Force $Out | Out-Null
$Names = @($Names | ForEach-Object { $_ -split ',' } | Where-Object { $_ })     # -File passes a,b,c as one string
$seen = 0; $t0 = Get-Date; $done = 0
while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutSec -and $done -lt $Names.Count) {
  Start-Sleep -Milliseconds 150
  $n = @(Get-ChildItem -Path $Watch -Filter "shot*.jpg" -ErrorAction SilentlyContinue).Count
  if ($n -gt $seen) {
    $seen = $n
    $p = Get-Process -Name $Process -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) {
      $r = New-Object NabooWin+RECT
      # the visible frame without the invisible resize border
      if ([NabooWin]::DwmGetWindowAttribute($p.MainWindowHandle, 9, [ref]$r, 16) -ne 0) { [void][NabooWin]::GetWindowRect($p.MainWindowHandle, [ref]$r) }
      $w = $r.R - $r.L; $h = $r.B - $r.T
      if ($w -gt 100 -and $h -gt 100) {
        $bmp = New-Object System.Drawing.Bitmap $w, $h
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($r.L, $r.T, 0, 0, (New-Object System.Drawing.Size $w, $h))
        $name = $Names[$done]
        $bmp.Save((Join-Path $Out ($name + "_window.png")), [System.Drawing.Imaging.ImageFormat]::Png)
        $g.Dispose(); $bmp.Dispose()
        Write-Output ("captured " + $name + " " + $w + "x" + $h + " title: " + $p.MainWindowTitle)
        $done++
      }
    }
  }
}
Write-Output ("windows captured: " + $done)
