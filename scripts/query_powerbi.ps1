param(
  [Parameter(Mandatory=$true)][string]$DaxPath,
  [Parameter(Mandatory=$true)][string]$OutputCsv
)
$ErrorActionPreference = 'Stop'
Add-Type -Path 'C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll'
$ws = Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop\AnalysisServicesWorkspaces'
$portFile = Get-ChildItem $ws -Filter 'msmdsrv.port.txt' -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (!$portFile) {throw 'Power BI Desktop Analysis Services not running'}
$port = (Get-Content $portFile.FullName -Encoding Unicode -Raw).Trim()
$conn = [Microsoft.AnalysisServices.AdomdClient.AdomdConnection]::new("Data Source=localhost:$port;")
try {
 $conn.Open()
 $cmd = $conn.CreateCommand()
 $cmd.CommandText = [IO.File]::ReadAllText($DaxPath)
 $cmd.CommandTimeout = 600
 $reader = $cmd.ExecuteReader()
 try {
   Add-Type -Path (Join-Path $PSScriptRoot 'FastCsvExport.cs') -ReferencedAssemblies @('System.dll','System.Data.dll','System.Core.dll')
   $dir=Split-Path -Parent $OutputCsv
   if (!(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
   $count = [FastCsvExport]::Export($reader,$OutputCsv)
   Write-Output "DAX_ROWS=$count; CSV=$OutputCsv"
 } finally {$reader.Close()}
} finally {$conn.Dispose()}
