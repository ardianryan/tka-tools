param(
    [string]$Source = "Flatbed",
    [string]$OutputDir,
    [string]$FilePrefix = "Scan",
    [string]$DeviceId = "auto",
    [string]$DeviceName = "auto",
    [int]$Dpi = 200
)

$wFormatJPEG = "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}"
$wia = New-Object -ComObject WIA.DeviceManager
$scannerInfo = $null

# 1. Match by DeviceID
if ($DeviceId -and $DeviceId -ne "auto") {
    foreach ($info in $wia.DeviceInfos) {
        if ($info.DeviceID -eq $DeviceId) {
            $scannerInfo = $info
            break
        }
    }
}

# 2. Match by DeviceName pattern
if (-not $scannerInfo -and $DeviceName -and $DeviceName -ne "auto") {
    foreach ($info in $wia.DeviceInfos) {
        if ($info.Properties.Item('Name').Value -like "*$DeviceName*") {
            $scannerInfo = $info
            break
        }
    }
}

# 3. Fallback: Select first available scanner device
if (-not $scannerInfo) {
    foreach ($info in $wia.DeviceInfos) {
        $scannerInfo = $info
        break
    }
}

if (-not $scannerInfo) {
    Write-Output "ERROR: Perangkat scanner tidak ditemukan. Pastikan scanner (Epson/Canon/HP/Brother/dll) terhubung."
    exit 1
}

$device = $scannerInfo.Connect()

# Configure Document Handling (1 = Flatbed, 2 = Feeder/ADF)
try {
    $handlingProp = $device.Properties.Item("Document Handling Select")
    if ($handlingProp) {
        if ($Source -eq "ADF") {
            $handlingProp.Value = 2
        } else {
            $handlingProp.Value = 1
        }
    }
} catch {
    # Flatbed-only scanner or unconfigurable feeder
}

$scannedFiles = @()
$counter = 1

do {
    try {
        $item = $device.Items(1)
        try {
            $item.Properties.Item("Horizontal Resolution").Value = $Dpi
            $item.Properties.Item("Vertical Resolution").Value = $Dpi
        } catch {}
        
        $image = $item.Transfer($wFormatJPEG)
        $timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
        $fileName = "$OutputDir\\${FilePrefix}_${timestamp}_$counter.jpg"
        $image.SaveFile($fileName)
        $scannedFiles += $fileName
        $counter++
        
        if ($Source -ne "ADF") {
            break
        }
    } catch {
        break
    }
} while ($Source -eq "ADF" -and $counter -le 100)

$res = @{
    success = $true
    count = $scannedFiles.Count
    files = $scannedFiles
    device = $scannerInfo.Properties.Item('Name').Value
}
$res | ConvertTo-Json -Compress
