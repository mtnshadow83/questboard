# Register Questboard as a toast notification app in the Windows registry
# Run once, elevated not required for HKCU

$appId = "Questboard.Notifications"
$regPath = "HKCU:\SOFTWARE\Classes\AppUserModelId\$appId"

if (-not (Test-Path $regPath)) {
    New-Item -Path $regPath -Force | Out-Null
}

Set-ItemProperty -Path $regPath -Name "DisplayName" -Value "Questboard" -Force
# Optional: set an icon path if we have one later
# Set-ItemProperty -Path $regPath -Name "IconUri" -Value "C:\path\to\icon.png" -Force

Write-Host "Registered app ID: $appId"
Write-Host "Registry: $regPath"
