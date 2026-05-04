$ErrorActionPreference = "Stop"

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class StreamDeckNativeMethods
{
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowTextLength(IntPtr hWnd);
}
"@

function Get-WindowTitle {
    param(
        [Parameter(Mandatory = $true)]
        [System.IntPtr]$Handle
    )

    $titleLength = [StreamDeckNativeMethods]::GetWindowTextLength($Handle)
    if ($titleLength -le 0) {
        return ""
    }

    $buffer = New-Object System.Text.StringBuilder ($titleLength + 1)
    [void][StreamDeckNativeMethods]::GetWindowText($Handle, $buffer, $buffer.Capacity)
    return $buffer.ToString()
}

$result = [ordered]@{
    ok = $false
    selected_paths = @()
    window_title = $null
    error = $null
}

try {
    $foregroundWindow = [StreamDeckNativeMethods]::GetForegroundWindow()
    $foregroundTitle = Get-WindowTitle -Handle $foregroundWindow
    $shell = New-Object -ComObject Shell.Application
    $candidateWindows = @()
    $matchedForegroundWindow = $false

    foreach ($window in $shell.Windows()) {
        if (-not $window) {
            continue
        }

        try {
            $windowHandle = [IntPtr]::new([int64]$window.HWND)
            $selectedItems = @($window.Document.SelectedItems())
            $selectedPaths = @()
            foreach ($item in $selectedItems) {
                if ($item -and $item.Path) {
                    $selectedPaths += [string]$item.Path
                }
            }

            if ($windowHandle -eq $foregroundWindow) {
                $matchedForegroundWindow = $true
                $result.window_title = [string]$window.LocationName
                $result.selected_paths = $selectedPaths
                if ($selectedPaths.Count -gt 0) {
                    $result.ok = $true
                    break
                }
                continue
            }

            if ($selectedPaths.Count -gt 0) {
                $candidateWindows += [ordered]@{
                    window_title = [string]$window.LocationName
                    selected_paths = $selectedPaths
                }
            }
        }
        catch {
            continue
        }
    }

    if (-not $result.ok) {
        if ($matchedForegroundWindow) {
            $result.error = "The focused Explorer window has no selected file."
        }
        elseif ($candidateWindows.Count -eq 1) {
            $result.ok = $true
            $result.window_title = [string]$candidateWindows[0].window_title
            $result.selected_paths = @($candidateWindows[0].selected_paths)
        }
        elseif ($candidateWindows.Count -gt 1) {
            $titleMatchedCandidates = @()
            if ($foregroundTitle) {
                $normalizedForegroundTitle = $foregroundTitle.Trim().ToLowerInvariant()
                $titleMatchedCandidates = @(
                    $candidateWindows | Where-Object {
                        $candidateTitle = [string]$_.window_title
                        $normalizedCandidateTitle = $candidateTitle.Trim().ToLowerInvariant()
                        $normalizedCandidateTitle -and (
                            $normalizedForegroundTitle -eq $normalizedCandidateTitle -or
                            $normalizedForegroundTitle.Contains($normalizedCandidateTitle) -or
                            $normalizedCandidateTitle.Contains($normalizedForegroundTitle)
                        )
                    }
                )
            }

            if ($titleMatchedCandidates.Count -eq 1) {
                $result.ok = $true
                $result.window_title = [string]$titleMatchedCandidates[0].window_title
                $result.selected_paths = @($titleMatchedCandidates[0].selected_paths)
            }
            else {
            $windowTitles = @($candidateWindows | ForEach-Object { $_.window_title } | Where-Object { $_ })
            if ($windowTitles.Count -gt 0) {
                $result.error = "Focused Explorer window could not be matched uniquely. Explorer windows with selected items: " + ($windowTitles -join ", ")
            }
            else {
                $result.error = "Focused Explorer window could not be matched uniquely. Multiple Explorer windows have selected items."
            }
            }
        }
        else {
            $result.error = "No focused Explorer window with a selected file was found."
        }
    }
}
catch {
    $result.error = $_.Exception.Message
}

$result | ConvertTo-Json -Compress
