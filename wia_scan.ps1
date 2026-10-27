param(
    [string]$Source = "Flatbed",
    [string]$OutputDir,
    [string]$FilePrefix = "Scan",
    [string]$DeviceId = "auto",
    [string]$DeviceName = "auto",
    [int]$Dpi = 200
)

$wFormatJPEG = "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}"
$convertFilterId = "{42A6E907-1D2F-4B38-AC50-31ADBE2AB3C2}"
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

# 3. Fallback: Prefer physical USB/WIA device (starting with {6BDD1FC6-) over virtual eSCL devices
if (-not $scannerInfo) {
    foreach ($info in $wia.DeviceInfos) {
        if ($info.DeviceID -like "{6BDD1FC6*") {
            $scannerInfo = $info
            break
        }
    }
    if (-not $scannerInfo) {
        foreach ($info in $wia.DeviceInfos) {
            $scannerInfo = $info
            break
        }
    }
}

if (-not $scannerInfo) {
    $res = @{
        success = $false
        msg = "Perangkat scanner tidak ditemukan. Pastikan scanner (Epson/Canon/HP/Brother/dll) terhubung melalui USB atau jaringan."
    }
    $res | ConvertTo-Json -Compress
    exit 0
}

# Connect with retry in case scanner is momentarily locked
$device = $null
for ($attempt = 1; $attempt -le 5; $attempt++) {
    try {
        $device = $scannerInfo.Connect()
        if ($device) { break }
    } catch {
        Start-Sleep -Milliseconds 800
    }
}

if (-not $device) {
    $res = @{
        success = $false
        msg = "Scanner sedang sibuk atau tidak merespons koneksi. Harap tunggu sesaat lalu coba kembali."
    }
    $res | ConvertTo-Json -Compress
    exit 0
}

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
} catch {}

# Configure Pages property (WIA Standard: 1 page per Transfer call in loop)
try {
    $pagesProp = $device.Properties.Item("Pages")
    if ($pagesProp) {
        $pagesProp.Value = 1
    }
} catch {}

$scannedFiles = @()
$counter = 1
$hasMorePages = $true
$consecutiveErrors = 0
$maxPages = 200

# Pra-pemeriksaan ADF: Cek sensor kertas di baki sebelum mulai
if ($Source -eq "ADF") {
    try {
        $initialStatus = $device.Properties.Item("Document Handling Status").Value
        if (($initialStatus -band 1) -eq 0) {
            Start-Sleep -Milliseconds 1500
            $initialStatus = $device.Properties.Item("Document Handling Status").Value
            if (($initialStatus -band 1) -eq 0) {
                $res = @{
                    success = $false
                    msg = "Baki ADF kosong atau kertas belum terdeteksi. Silakan pasang tumpukan dokumen ke tray ADF printer Epson."
                }
                $res | ConvertTo-Json -Compress
                exit 0
            }
        }
    } catch {}
}

# Helper ImageProcess untuk kompresi real JPEG (menghindari raw BMP 14 MB)
$ip = $null
try {
    $ip = New-Object -ComObject WIA.ImageProcess
    $ip.Filters.Add($convertFilterId)
    $ip.Filters.Item(1).Properties.Item("FormatID").Value = $wFormatJPEG
    $ip.Filters.Item(1).Properties.Item("Quality").Value = 85
} catch {
    $ip = $null
}

while ($hasMorePages -and $counter -le $maxPages) {
    try {
        $item = $device.Items(1)
        try {
            $item.Properties.Item("Horizontal Resolution").Value = $Dpi
            $item.Properties.Item("Vertical Resolution").Value = $Dpi
        } catch {}
        
        $rawImage = $item.Transfer($wFormatJPEG)
        
        # Kompresi ke JPEG standar jika tersedia filter converter
        $finalImage = $rawImage
        if ($ip) {
            try {
                $finalImage = $ip.Apply($rawImage)
            } catch {
                $finalImage = $rawImage
            }
        }
        
        # Simpan SATU PER SATU langsung ke direktori tujuan (inbox/)
        $timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
        $fileName = "$OutputDir\\${FilePrefix}_${timestamp}_$counter.jpg"
        $finalImage.SaveFile($fileName)
        $scannedFiles += $fileName
        $counter++
        $consecutiveErrors = 0
        
        if ($Source -ne "ADF") {
            # Flatbed cukup 1 halaman
            break
        }
        
        # Jeda sejenak agar mekanik ADF siap menarik lembar berikutnya
        Start-Sleep -Milliseconds 1000
        
        # Cek status sensor kertas setelah lembar selesai ditarik
        try {
            $currStatus = $device.Properties.Item("Document Handling Status").Value
            if (($currStatus -band 1) -eq 0) {
                # Beri jeda konfirmasi 1 detik memastikan apakah tumpukan benar-benar habis
                Start-Sleep -Milliseconds 1200
                $currStatus = $device.Properties.Item("Document Handling Status").Value
                if (($currStatus -band 1) -eq 0) {
                    $hasMorePages = $false
                    break
                }
            }
        } catch {}
        
    } catch {
        $ex = $_.Exception
        $hresult = if ($ex -and $ex.HResult) { $ex.HResult } else { 0 }
        $msg = if ($ex) { $ex.Message.ToLower() } else { "" }
        
        # 1. 0x80210003 (-2145320957) = WIA_ERROR_PAPER_EMPTY (kertas habis total)
        if ($hresult -eq -2145320957 -or $msg -like "*empty*" -or $msg -like "*0x80210003*") {
            $hasMorePages = $false
            break
        }
        
        # 2. Cek apakah sensor ADF masih mendeteksi kertas
        $isPaperPresent = $true
        try {
            $status = $device.Properties.Item("Document Handling Status").Value
            if (($status -band 1) -eq 0) {
                $isPaperPresent = $false
            }
        } catch {}
        
        # Jika sensor baki sudah kosong dan sudah ada berkas yang tersimpan:
        if (-not $isPaperPresent -and $scannedFiles.Count -gt 0 -and $consecutiveErrors -ge 3) {
            $hasMorePages = $false
            break
        }
        
        # 3. Scanner sibuk / sedang memutar rol / transisi lembar:
        # TETAP RETRY hingga 35 kali (~45 detik toleransi mekanik)
        if ($consecutiveErrors -lt 35) {
            $consecutiveErrors++
            Start-Sleep -Milliseconds 1200
            continue
        }
        
        # Jika sudah mencoba 35 kali berturut-turut dan gagal:
        break
    }
}

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
