$ErrorActionPreference = 'Stop'
Add-Type -Path 'C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll'
$folder=Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop\AnalysisServicesWorkspaces'
$pf=Get-ChildItem $folder -Filter msmdsrv.port.txt -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$port=(Get-Content $pf.FullName -Encoding Unicode -Raw).Trim()
$server=[Microsoft.AnalysisServices.Tabular.Server]::new()
$server.Connect("localhost:$port")
try{
 foreach($database in $server.Databases){
   Write-Output "DATABASE $($database.Name) | ID $($database.ID)"
   foreach($expr in $database.Model.Expressions) {Write-Output ("EXPR "+$expr.Name+" = "+$expr.Expression.Substring(0,[Math]::Min(240,$expr.Expression.Length)))}
   foreach($table in $database.Model.Tables) {
     foreach($partition in $table.Partitions){
       $source=$partition.Source
       $str=if($source -and $source.PSObject.Properties['Expression']){$source.Expression}else{[string]$source}
       Write-Output "PART $($table.Name) : $($partition.Name) : TYPE=$($source.GetType().Name) : $($str.Substring(0,[Math]::Min(270,$str.Length)))"
     }
   }
 }
}finally{$server.Disconnect()}
