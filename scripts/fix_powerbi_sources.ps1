$ErrorActionPreference='Stop'
$root='C:\Users\user\Customer Churn Early-Warning System'
$old='C:\Users\user\Downloads\'
$new='C:\Users\user\Customer Churn Early-Warning System\data\raw\'
@('transactions_data.csv','customer_data.csv') | ForEach-Object {
 if (!(Test-Path (Join-Path $new $_))) {throw "Missing raw source: $_"}
}
Add-Type -Path 'C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll'
$base=Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop\AnalysisServicesWorkspaces'
$pf=Get-ChildItem $base -Filter msmdsrv.port.txt -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (!$pf) {throw 'Open the project PBIX in Power BI Desktop before updating its live source definitions'}
$port=(Get-Content $pf.FullName -Encoding Unicode -Raw).Trim()
$s=[Microsoft.AnalysisServices.Tabular.Server]::new()
$s.Connect("localhost:$port")
try {
 if($s.Databases.Count -ne 1) {throw 'Unexpected model count: '+$s.Databases.Count}
 $model=$s.Databases[0].Model
 $updates=0
 foreach($name in @('transactions_data','customer_data')) {
  $expr=$model.Expressions[$name]
  if(!$expr) {throw "Missing model expression: $name"}
  $from=$old + $(if($name -eq 'transactions_data'){'transactions_data.csv'}else{'customer_data.csv'})
  $to=$new + $(if($name -eq 'transactions_data'){'transactions_data.csv'}else{'customer_data.csv'})
  $fromM=$from.Replace('\','\\')
  $toM=$to.Replace('\','\\')
  # M code contains literal Windows backslashes (Power Query does not double-escape).
  if ($expr.Expression.Contains($from)) {
   $expr.Expression = $expr.Expression.Replace($from,$to)
   $updates++
   Write-Output "UPDATED $name"
  } elseif($expr.Expression.Contains($to)) {Write-Output "ALREADY_CORRECT $name"}
  else {throw "Unexpected source expression for $name; no change"}
 }
 if ($updates -gt 0) {$model.SaveChanges(); Write-Output "MODEL_SAVED=$updates"}
 foreach($name in @('transactions_data','customer_data')){
  $expr=$model.Expressions[$name]
  Write-Output "CURRENT $name : $($expr.Expression.Split([Environment]::NewLine)[1].Trim())"
 }
}finally{$s.Disconnect()}
