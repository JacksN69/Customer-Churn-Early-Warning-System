$ErrorActionPreference='Stop'
Add-Type -Path 'C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll'
$pf=Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop\AnalysisServicesWorkspaces') -Filter msmdsrv.port.txt -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$port=(Get-Content $pf.FullName -Encoding Unicode -Raw).Trim()
$s=[Microsoft.AnalysisServices.Tabular.Server]::new()
$s.Connect("localhost:$port")
try {
 $t=$s.Databases[0].Model.Tables['DimCustomer']
 foreach($name in 'CreditUtilizationStatus','FeatureRequestsDisplay','ComplaintTopicsDisplay'){
  $c=$t.Columns[$name]
  Write-Output "COLUMN $name | $($c.GetType().Name) | $($c.DataType) | $($c.Expression)"
 }
 $m=$s.Databases[0].Model
 $m.RequestRefresh([Microsoft.AnalysisServices.Tabular.RefreshType]::Calculate)
 $m.SaveChanges() | Out-Null
 Write-Output 'CALCULATE_REFRESH_COMPLETE'
} finally {$s.Disconnect()}
