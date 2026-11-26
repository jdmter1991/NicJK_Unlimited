# Capture the game window (first nicjk.x86_64 process) to a PNG.   capture_once.ps1 -Out file.png
param([string]$Out)
Add-Type -AssemblyName System.Drawing
Add-Type 'using System;using System.Runtime.InteropServices;public class W1{[DllImport("user32.dll")]public static extern bool GetWindowRect(IntPtr h,out RECT r);public struct RECT{public int L,T,R,B;}}'
$p = Get-Process nicjk.x86_64 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($p) { $r = New-Object W1+RECT; [W1]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
  $b = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T); $g = [System.Drawing.Graphics]::FromImage($b)
  $g.CopyFromScreen($r.L, $r.T, 0, 0, $b.Size); $b.Save($Out) }
