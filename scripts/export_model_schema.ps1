$ErrorActionPreference='Stop'
$root='C:\Users\user\Customer Churn Early-Warning System'
Add-Type -Path 'C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll'
$f=Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop\AnalysisServicesWorkspaces') -Recurse -Filter msmdsrv.port.txt | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$port=(Get-Content $f.FullName -Encoding Unicode -Raw).Trim()
$s=[Microsoft.AnalysisServices.Tabular.Server]::new();$s.Connect("localhost:$port")
try{
 $items=@()
 foreach($t in $s.Databases[0].Model.Tables){
  if($t.Name -notin @('CustomerMonthly','ChurnFeatures','DimCustomer')){continue}
  foreach($col in $t.Columns) {
   $items += [pscustomobject]@{table=$t.Name;column=$col.Name;data_type=$col.DataType.ToString()}
  }
 }
 $items | Export-Csv "$root\reports\powerbi_model_schema_private.csv" -NoTypeInformation -Encoding UTF8
 foreach($name in @('CustomerMonthly','ChurnFeatures','DimCustomer')) {
 $cols=@($items|Where-Object {$_.table -eq $name})
 Write-Output "$name cols=$($cols.Count)"
 }
}finally{$s.Disconnect()}
