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

# Configure Document Handling (WIA Standard: 1 = Feeder/ADF, 2 = Flatbed)
try {
    $handlingProp = $device.Properties.Item("Document Handling Select")
    if ($handlingProp) {
        if ($Source -eq "ADF") {
            $handlingProp.Value = 1  # 1 = FEEDER / ADF
        } else {
            $handlingProp.Value = 2  # 2 = FLATBED
        }
    }
} catch {
    # Flatbed-only scanner or unconfigurable feeder
}

# Configure Pages property if available
try {
    $pagesProp = $device.Properties.Item("Pages")
    if ($pagesProp) {
        $pagesProp.Value = 1
    }
} catch {}

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
        # Feeder ran out of paper or scan completed
        break
    }
} while ($Source -eq "ADF" -and $counter -le 100)

if ($scannedFiles.Count -eq 0) {
    $res = @{
        success = $false
        msg = if ($Source -eq "ADF") { "Baki ADF kosong atau kertas tidak terdeteksi. Silakan masukkan tumpukan dokumen ke feeder ADF." } else { "Tidak ada dokumen di kaca flatbed." }
    }
    $res | ConvertTo-Json -Compress
    exit 0
}

$res = @{
    success = $true
    count = $scannedFiles.Count
    files = $scannedFiles
    device = $scannerInfo.Properties.Item('Name').Value
}
$res | ConvertTo-Json -Compress
