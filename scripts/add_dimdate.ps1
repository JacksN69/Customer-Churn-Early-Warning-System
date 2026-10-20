$ErrorActionPreference='Stop'
# Adds a monthly DimDate calculated table and its relationships to the OPEN Power BI Desktop model.
# Idempotent. Remember to save the PBIX (Ctrl+S) afterwards.
$root='C:\Users\user\Customer Churn Early-Warning System'
Add-Type -Path 'C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll'
$T='Microsoft.AnalysisServices.Tabular'
$pf=Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop\AnalysisServicesWorkspaces') -Filter msmdsrv.port.txt -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$port=(Get-Content $pf.FullName -Encoding Unicode -Raw).Trim()
$dax=@'
VAR FirstMonth = DATE ( YEAR ( MIN ( ChurnFeatures[Month] ) ), MONTH ( MIN ( ChurnFeatures[Month] ) ), 1 )
VAR MonthSpan = DATEDIFF ( FirstMonth, MAX ( ChurnFeatures[Month] ), MONTH )
RETURN
    ADDCOLUMNS (
        SELECTCOLUMNS ( GENERATESERIES ( 0, MonthSpan ), "Date", EDATE ( FirstMonth, [Value] ) ),
        "Year", YEAR ( [Date] ),
        "MonthNumber", MONTH ( [Date] ),
        "MonthName", FORMAT ( [Date], "mmmm" ),
        "YearMonth", FORMAT ( [Date], "yyyy-MM" ),
        "YearMonthSort", YEAR ( [Date] ) * 100 + MONTH ( [Date] ),
        "Quarter", "Q" & ROUNDUP ( MONTH ( [Date] ) / 3, 0 )
    )
'@
$s=New-Object "$T.Server"; $s.Connect("localhost:$port")
try{
 if($s.Databases.Count -ne 1){throw 'Unexpected model count'}
 $m=$s.Databases[0].Model
 if(-not $m.Tables.Contains('DimDate')){
   $tbl=New-Object "$T.Table"; $tbl.Name='DimDate'
   $p=New-Object "$T.Partition"; $p.Name='DimDate'
   $src=New-Object "$T.CalculatedPartitionSource"; $src.Expression=$dax
   $p.Source=$src; $tbl.Partitions.Add($p)
   $m.Tables.Add($tbl)
   $m.SaveChanges() | Out-Null
   Write-Output 'DIMDATE_TABLE_CREATED'
 } else { Write-Output 'DIMDATE_ALREADY_PRESENT' }
}finally{$s.Disconnect()}

# Reconnect to get a fresh model (calculated columns are created on first calculation)
$s=New-Object "$T.Server"; $s.Connect("localhost:$port")
try{
 $m=$s.Databases[0].Model
 $d=$m.Tables['DimDate']
 Write-Output ("DimDate columns: " + (($d.Columns | % Name) -join ', '))
 $d.Columns['MonthName'].SortByColumn=$d.Columns['MonthNumber']
 $d.Columns['YearMonth'].SortByColumn=$d.Columns['YearMonthSort']
 $d.DataCategory='Time'
 $d.Columns['Date'].IsKey=$true
 $d.Columns['Date'].FormatString='mmm yyyy'
 foreach($pair in @(@('ChurnFeatures','Month'),@('CustomerMonthly','Month'))){
   $rname="$($pair[0])_$($pair[1])_DimDate"
   if(-not ($m.Relationships | ? { $_.Name -eq $rname })){
     $r=New-Object "$T.SingleColumnRelationship"
     $r.Name=$rname
     $r.FromColumn=$m.Tables[$pair[0]].Columns[$pair[1]]
     $r.ToColumn=$d.Columns['Date']
     $r.FromCardinality='Many'; $r.ToCardinality='One'
     $r.CrossFilteringBehavior='OneDirection'
     $m.Relationships.Add($r)
     Write-Output "RELATIONSHIP_ADDED $rname"
   }
 }
 $m.Tables['DimDate'].RequestRefresh('Full')
 $m.SaveChanges() | Out-Null
 Write-Output 'MODEL_SAVED_AND_DIMDATE_REFRESHED'
 [IO.File]::WriteAllText("$root\powerbi\dim_date.dax","DimDate =`r`n$dax",[Text.UTF8Encoding]::new($false))
}finally{$s.Disconnect()}
