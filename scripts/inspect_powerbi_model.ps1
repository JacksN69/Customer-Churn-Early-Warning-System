$ErrorActionPreference = "Stop"
$asm = 'C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll'
Add-Type -Path $asm
$workspaces = Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop\AnalysisServicesWorkspaces'
$portFile = Get-ChildItem $workspaces -Filter 'msmdsrv.port.txt' -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $portFile) { throw 'No running Power BI local engine found' }
$port = (Get-Content $portFile.FullName -Encoding Unicode -Raw).Trim()
Write-Output "Connecting to localhost:$port"
$conn = [Microsoft.AnalysisServices.AdomdClient.AdomdConnection]::new("Data Source=localhost:$port;")
try {
  $conn.Open()
  foreach ($q in @('SELECT * FROM $SYSTEM.TMSCHEMA_TABLES','EVALUATE ROW("Test",1)')) {
    Write-Output "Query: $q"
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = $q
    $reader = $cmd.ExecuteReader()
    $fields = @()
    for ($i=0; $i -lt $reader.FieldCount; $i++) { $fields += $reader.GetName($i) }
    Write-Output ("Columns: " + ($fields -join ', '))
    $n=0
    while ($reader.Read() -and $n -lt 50) {
      $obj = [ordered]@{}
      for ($i=0; $i -lt $reader.FieldCount; $i++) { if ($fields[$i] -match 'Name|ID|Test') { $obj[$fields[$i]] = [string]$reader.GetValue($i) } }
      Write-Output (($obj | ConvertTo-Json -Compress))
      $n++
    }
    $reader.Close()
  }
} finally { $conn.Dispose() }
