param([string]$KitPath = (Join-Path $PSScriptRoot '../demo-upload-kit'))
$ErrorActionPreference = 'Stop'
$kitRoot = (Resolve-Path -LiteralPath $KitPath).Path
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$word.AutomationSecurity = 3
try {
    foreach ($folder in @('resumes', 'supporting')) {
        foreach ($file in Get-ChildItem -LiteralPath (Join-Path $kitRoot $folder) -Filter '*.docx' -File) {
            $document = $word.Documents.Open($file.FullName, $false, $true)
            try {
                $pdfPath = [System.IO.Path]::ChangeExtension($file.FullName, '.pdf')
                $document.ExportAsFixedFormat($pdfPath, 17)
                Write-Output $pdfPath
            }
            finally {
                $document.Close(0)
                [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($document)
            }
        }
    }
}
finally {
    $word.Quit(0)
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}
