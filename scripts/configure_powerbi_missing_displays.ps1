$ErrorActionPreference='Stop'
$root='C:\Users\user\Customer Churn Early-Warning System'
$pbix=Join-Path $root 'powerbi\Customer Churn Early-Warning System.pbix'
$backup=Join-Path $root 'powerbi\backups\Customer Churn Early-Warning System.before-missing-value-labels.pbix'
if(!(Test-Path $backup)){Copy-Item $pbix $backup -ErrorAction Stop}
Add-Type -Path 'C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll'
$pf=Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop\AnalysisServicesWorkspaces') -Filter msmdsrv.port.txt -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if(!$pf){throw 'Power BI Desktop local model not running'}
$port=(Get-Content $pf.FullName -Encoding Unicode -Raw).Trim()
$server=[Microsoft.AnalysisServices.Tabular.Server]::new()
$server.Connect("localhost:$port")
try{
 if($server.Databases.Count -ne 1){throw 'Multiple databases found; abort'}
 $model=$server.Databases[0].Model
 $dim=$model.Tables['DimCustomer']
 if(!$dim){throw 'Missing DimCustomer'}
 $expressions=[ordered]@{
  'CreditUtilizationStatus'='IF ( ISBLANK ( DimCustomer[credit_utilization_ratio] ), IF ( DimCustomer[credit_card] = FALSE(), "Not applicable (no credit card)", "Not recorded" ), "Recorded" )'
  'FeatureRequestsDisplay'='IF ( ISBLANK ( DimCustomer[feature_requests] ) || TRIM ( DimCustomer[feature_requests] ) = "", "Not recorded", DimCustomer[feature_requests] )'
  'ComplaintTopicsDisplay'='IF ( ISBLANK ( DimCustomer[complaint_topics] ) || TRIM ( DimCustomer[complaint_topics] ) = "", "Not recorded", DimCustomer[complaint_topics] )'
 }
 foreach($key in $expressions.Keys){
  $existing=$dim.Columns[$key]
  if($existing -and $existing.Expression -ne $expressions[$key]){throw "Existing differently defined column: $key"}
  if(!$existing){
    $col=[Microsoft.AnalysisServices.Tabular.CalculatedColumn]::new()
    $col.Name=$key
    $col.DataType=[Microsoft.AnalysisServices.Tabular.DataType]::String
    $col.Expression=$expressions[$key]
    $dim.Columns.Add($col)
    Write-Output "ADDED_CALCULATED_COLUMN $key"
  } else {Write-Output "ALREADY_PRESENT $key"}
 }
 $model.SaveChanges() | Out-Null
 Write-Output 'MODEL_CALCULATED_COLUMNS_SAVED'
} finally {$server.Disconnect()}
