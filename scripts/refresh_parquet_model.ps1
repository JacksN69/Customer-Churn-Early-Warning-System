$ErrorActionPreference='Stop'
Add-Type -Path 'C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll'
$pf=Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop\AnalysisServicesWorkspaces') -Filter msmdsrv.port.txt -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$port=(Get-Content $pf.FullName -Encoding Unicode -Raw).Trim()
$s=[Microsoft.AnalysisServices.Tabular.Server]::new()
$s.Connect("localhost:$port")
try{
 $m=$s.Databases[0].Model
 foreach($name in @('CustomerMonthly','ChurnFeatures','DimCustomer')){
   $m.Tables[$name].RequestRefresh([Microsoft.AnalysisServices.Tabular.RefreshType]::Full)
   Write-Output "REQUESTED_REFRESH $name"
 }
 $r=$m.SaveChanges()
 Write-Output "REFRESH_COMPLETED"
}finally{$s.Disconnect()}
