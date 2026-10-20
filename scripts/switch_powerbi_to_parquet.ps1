$ErrorActionPreference='Stop'
$root='C:\Users\user\Customer Churn Early-Warning System'
$parquet=Join-Path $root 'data\processed'
$map=@{
 'CustomerMonthly'='customer_monthly.parquet'
 'ChurnFeatures'='churn_features.parquet'
 'DimCustomer'='dim_customer.parquet'
}
Add-Type -Path 'C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll'
$pf=Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop\AnalysisServicesWorkspaces') -Filter msmdsrv.port.txt -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$port=(Get-Content $pf.FullName -Encoding Unicode -Raw).Trim()
$server=[Microsoft.AnalysisServices.Tabular.Server]::new()
$server.Connect("localhost:$port")
try {
 if($server.Databases.Count -ne 1){throw 'Unexpected model count'}
 $model=$server.Databases[0].Model
 foreach($tableName in $map.Keys) {
  $file=Join-Path $parquet $map[$tableName]
  if(!(Test-Path $file)){throw "Missing file: $file"}
  $table=$model.Tables[$tableName]
  if(!$table){throw "Missing Power BI table: $tableName"}
  $source=$table.Partitions[0].Source
  if($source.GetType().Name -ne 'MPartitionSource'){throw "Unexpected partition type for $tableName"}
  $m="let`n    Source = Parquet.Document(File.Contents(`"$file`"))`nin`n    Source"
  $source.Expression=$m
  Write-Output "PARQUET_SOURCE_ASSIGNED $tableName $file"
 }
 $result=$model.SaveChanges()
 Write-Output "PARTITIONS_MODEL_SAVED"
 foreach($tableName in $map.Keys){
   $source=$model.Tables[$tableName].Partitions[0].Source.Expression
   if(!$source.Contains('Parquet.Document')){throw "Changed M expression not persisted for $tableName"}
   $export=@{'CustomerMonthly'='customer_monthly.m.txt'; 'ChurnFeatures'='churn_features.m.txt'; 'DimCustomer'='DimCustomer.txt'}[$tableName]
   [IO.File]::WriteAllText((Join-Path "$root\powerquery" $export),$source,[Text.UTF8Encoding]::new($false))
   Write-Output "M_EXPORT_UPDATED $export"
 }
}finally{$server.Disconnect()}
