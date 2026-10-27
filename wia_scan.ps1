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

# Configure Pages property (WIA Standard: 1 page per Transfer call in loop)
try {
    $pagesProp = $device.Properties.Item("Pages")
    if ($pagesProp) {
        $pagesProp.Value = 1  # 1 lembar per siklus transfer COM
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
            # Tunggu 1.5 detik barangkali kertas baru saja dimasukkan
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

while ($hasMorePages -and $counter -le $maxPages) {
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
        $consecutiveErrors = 0
        
        if ($Source -ne "ADF") {
            # Pemindaian flatbed cukup 1 halaman
            break
        }
        
        # Jeda sejenak agar mekanik ADF siap menarik lembar berikutnya
        Start-Sleep -Milliseconds 1200
        
    } catch {
        $ex = $_.Exception
        $hresult = if ($ex -and $ex.HResult) { $ex.HResult } else { 0 }
        $msg = if ($ex) { $ex.Message.ToLower() } else { "" }
        
        # 1. 0x80210003 (-2145320957) = WIA_ERROR_PAPER_EMPTY (seluruh lembar di baki ADF telah habis dipindai)
        if ($hresult -eq -2145320957 -or $msg -like "*empty*" -or $msg -like "*0x80210003*") {
            $hasMorePages = $false
            break
        }
        
        # 2. Scanner sibuk / sedang memutar rol / menarik lembar berikutnya (0x80210006, warming up, dll)
        $isBusy = ($hresult -eq -2145320954 -or $msg -like "*busy*" -or $msg -like "*0x80210006*" -or 
                   $msg -like "*warming*" -or $msg -like "*not ready*" -or $hresult -eq -2147467259 -or
                   $msg -like "*device is not ready*" -or $msg -like "*80004005*")
                   
        if ($isBusy -and $consecutiveErrors -lt 35) {
            $consecutiveErrors++
            Start-Sleep -Milliseconds 1500
            continue
        }
        
        # 3. Jika sensor feeder masih mendeteksi kertas, beri kesempatan rol menarik
        try {
            $status = $device.Properties.Item("Document Handling Status").Value
            if (($status -band 1) -eq 1 -and $consecutiveErrors -lt 25) {
                $consecutiveErrors++
                Start-Sleep -Seconds 2
                continue
            }
        } catch {}
        
        # 4. Jika sudah ada minimal 1 lembar yang berhasil dipindai dan terjadi akhir dokumen:
        if ($scannedFiles.Count -gt 0) {
            $hasMorePages = $false
            break
        }
        
        # 5. Jika belum ada lembar yang terpindai sama sekali, laporkan error
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
