param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$PowerBIBin = 'C:\Program Files\Microsoft Power BI Desktop\bin'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path $ProjectRoot).Path
$pbix = Join-Path $root 'powerbi\Customer Churn Early-Warning System.pbix'
if (-not (Test-Path -LiteralPath $pbix)) {
    throw "Local PBIX not found: $pbix. The PBIX is not included in the public repository."
}
$backupDir = Join-Path $root 'powerbi\backups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$backupFile = Join-Path $backupDir 'Customer Churn Early-Warning System.before-dashboard-20261020.pbix'
if (-not (Test-Path $backupFile)) {
    Copy-Item -Path $pbix -Destination $backupFile -Force
    Write-Output "BACKUP_CREATED: $backupFile"
}

$tabularDll = Join-Path $PowerBIBin 'Microsoft.AnalysisServices.Server.Tabular.dll'
if (-not (Test-Path -LiteralPath $tabularDll)) {
    throw "Power BI Tabular assembly not found: $tabularDll. Pass -PowerBIBin for a custom installation."
}
Add-Type -Path $tabularDll
$T = 'Microsoft.AnalysisServices.Tabular'

function Get-PbiPort {
    $wsRoot = Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop\AnalysisServicesWorkspaces'
    if (-not (Test-Path $wsRoot)) { return $null }
    $pf = Get-ChildItem $wsRoot -Filter msmdsrv.port.txt -Recurse -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($null -eq $pf) { return $null }
    $p = (Get-Content $pf.FullName -Encoding Unicode -Raw).Trim()
    if ([string]::IsNullOrWhiteSpace($p)) { return $null }
    return $p
}

function Wait-ForModel {
    param([int]$MaxSeconds = 60)
    $elapsed = 0
    while ($elapsed -lt $MaxSeconds) {
        $p = Get-PbiPort
        if ($null -ne $p) {
            try {
                $srv = New-Object "$T.Server"
                $srv.Connect("localhost:$p")
                $cnt = $srv.Databases.Count
                $srv.Disconnect()
                if ($cnt -ge 1) { return $p }
            } catch {}
        }
        Start-Sleep -Seconds 2
        $elapsed += 2
    }
    return $null
}

$port = Wait-ForModel -MaxSeconds 8
if ($null -eq $port) {
    $procs = Get-Process PBIDesktop -ErrorAction SilentlyContinue
    if ($procs) {
        throw "Power BI Desktop is already running, but its model is not available. Open the intended PBIX and retry. Existing processes and files were left untouched."
    }
    $powerBIExe = Join-Path $PowerBIBin 'PBIDesktop.exe'
    if (-not (Test-Path -LiteralPath $powerBIExe)) {
        throw "Power BI Desktop executable not found: $powerBIExe. Pass -PowerBIBin for a custom installation."
    }
    Write-Output "Starting Power BI Desktop..."
    Start-Process -FilePath $powerBIExe -ArgumentList "`"$pbix`""
    $port = Wait-ForModel -MaxSeconds 90
}
if ($null -eq $port) { throw "Could not find running Power BI Desktop AnalysisServices model." }
Write-Output "CONNECTED_PORT_WITH_MODEL: $port"

$schemas = Get-Content (Join-Path $root 'outputs\powerbi_table_schemas.json') -Raw -Encoding UTF8 | ConvertFrom-Json

# PASS 1: Create M tables, Calculated Tables, and Calculated Columns
$s = New-Object "$T.Server"
$s.Connect("localhost:$port")
try {
    $m = $s.Databases[0].Model

    # 1. Add Parquet M tables
    foreach ($tblName in @('ChurnPredictions', 'FeatureImportance', 'ModelExperiments', 'FeatureRegistry')) {
        $meta = $schemas.$tblName
        if (-not $m.Tables.Contains($tblName)) {
            $tbl = New-Object "$T.Table"
            $tbl.Name = $tblName

            foreach ($c in $meta.columns) {
                $col = New-Object "$T.DataColumn"
                $col.Name = $c.name
                $col.SourceColumn = $c.name
                $col.DataType = [Microsoft.AnalysisServices.Tabular.DataType]::($c.dataType)
                $col.SummarizeBy = [Microsoft.AnalysisServices.Tabular.AggregateFunction]::None
                $tbl.Columns.Add($col)
            }

            $part = New-Object "$T.Partition"
            $part.Name = $tblName
            $part.Mode = [Microsoft.AnalysisServices.Tabular.ModeType]::Import
            $src = New-Object "$T.MPartitionSource"
            $escapedPath = $meta.path
            $src.Expression = "let`r`n    Source = Parquet.Document(File.Contents(""$escapedPath""))`r`nin`r`n    Source"
            $part.Source = $src
            $tbl.Partitions.Add($part)

            $m.Tables.Add($tbl)
            Write-Output "M_TABLE_ADDED: $tblName"
        } else {
            # Ensure any new columns in schema exist on ChurnPredictions
            $tbl = $m.Tables[$tblName]
            foreach ($c in $meta.columns) {
                if (-not $tbl.Columns.Contains($c.name)) {
                    $col = New-Object "$T.DataColumn"
                    $col.Name = $c.name
                    $col.SourceColumn = $c.name
                    $col.DataType = [Microsoft.AnalysisServices.Tabular.DataType]::($c.dataType)
                    $col.SummarizeBy = [Microsoft.AnalysisServices.Tabular.AggregateFunction]::None
                    $tbl.Columns.Add($col)
                    Write-Output "M_COLUMN_ADDED: $tblName[$($c.name)]"
                }
            }
        }
        $m.Tables[$tblName].RequestRefresh([Microsoft.AnalysisServices.Tabular.RefreshType]::Full)
    }

    $m.SaveChanges() | Out-Null
    Write-Output "PASS_1A_M_TABLES_REFRESHED"
} finally {
    $s.Disconnect()
}

# PASS 2: Add Calculated Columns, Calculated Tables, and Relationships
$s = New-Object "$T.Server"
$s.Connect("localhost:$port")
try {
    $m = $s.Databases[0].Model

    function Ensure-CalcColumn($table, $colName, $daxExpr, $dataType = 'String') {
        $tblObj = $m.Tables[$table]
        if (-not $tblObj.Columns.Contains($colName)) {
            $cc = New-Object "$T.CalculatedColumn"
            $cc.Name = $colName
            $cc.Expression = $daxExpr
            $cc.DataType = [Microsoft.AnalysisServices.Tabular.DataType]::$dataType
            $cc.SummarizeBy = [Microsoft.AnalysisServices.Tabular.AggregateFunction]::None
            $tblObj.Columns.Add($cc)
            Write-Output "CALC_COL_ADDED: $table[$colName]"
        } else {
            $cc = $tblObj.Columns[$colName]
            if ($cc -is [Microsoft.AnalysisServices.Tabular.CalculatedColumn]) {
                $cc.Expression = $daxExpr
            }
        }
    }

    # DimDate helper columns
    Ensure-CalcColumn 'DimDate' 'IsEligibleWindow' 'IF ( DimDate[YearMonthSort] >= 202306 && DimDate[YearMonthSort] <= 202311, 1, 0 )' 'Int64'
    Ensure-CalcColumn 'DimDate' 'EligibleMonthFlag' 'IF ( DimDate[YearMonthSort] >= 202306 && DimDate[YearMonthSort] <= 202311, "Ja", "Nein" )' 'String'
    Ensure-CalcColumn 'DimDate' 'PipelinePhase' 'SWITCH ( TRUE(), DimDate[YearMonthSort] <= 202305, "1. Historie-Aufbau (Jan-Mai)", DimDate[YearMonthSort] <= 202309, "2. Training (Jun-Sep)", DimDate[YearMonthSort] = 202310, "3. Validierung (Okt)", DimDate[YearMonthSort] = 202311, "4. Test Out-of-Sample (Nov)", "5. Produktion Scoring (Dez -> Jan)" )' 'String'
    Ensure-CalcColumn 'DimDate' 'PipelinePhaseSort' 'SWITCH ( TRUE(), DimDate[YearMonthSort] <= 202305, 1, DimDate[YearMonthSort] <= 202309, 2, DimDate[YearMonthSort] = 202310, 3, DimDate[YearMonthSort] = 202311, 4, 5 )' 'Int64'

    # ChurnFeatures helper columns
    Ensure-CalcColumn 'ChurnFeatures' 'EligibleRowFlag' 'IF ( ChurnFeatures[EligibleForTraining] = 1, "Ja", "Nein" )' 'String'
    Ensure-CalcColumn 'ChurnFeatures' 'AvgTransactionCount_3M' 'DIVIDE ( ChurnFeatures[TransactionCount_Recent3M], 3.0 )' 'Double'
    Ensure-CalcColumn 'ChurnFeatures' 'AvgTransactionCount_6M' 'IF ( ChurnFeatures[Has6MonthHistory] = 1, DIVIDE ( ChurnFeatures[TransactionCount_Recent3M] + ChurnFeatures[TransactionCount_Previous3M], 6.0 ), BLANK() )' 'Double'
    Ensure-CalcColumn 'ChurnFeatures' 'RecencyBin' 'SWITCH ( TRUE(), ChurnFeatures[EligibleForTraining] <> 1 || ISBLANK ( ChurnFeatures[DaysSinceLastTransaction] ), BLANK(), ChurnFeatures[DaysSinceLastTransaction] = 0, "0 Tage (Monatsende)", ChurnFeatures[DaysSinceLastTransaction] <= 3, "1-3 Tage", ChurnFeatures[DaysSinceLastTransaction] <= 7, "4-7 Tage", ChurnFeatures[DaysSinceLastTransaction] <= 14, "8-14 Tage", ChurnFeatures[DaysSinceLastTransaction] <= 21, "15-21 Tage", "22-31 Tage" )' 'String'
    Ensure-CalcColumn 'ChurnFeatures' 'RecencyBinSort' 'SWITCH ( TRUE(), ChurnFeatures[EligibleForTraining] <> 1 || ISBLANK ( ChurnFeatures[DaysSinceLastTransaction] ), 99, ChurnFeatures[DaysSinceLastTransaction] = 0, 1, ChurnFeatures[DaysSinceLastTransaction] <= 3, 2, ChurnFeatures[DaysSinceLastTransaction] <= 7, 3, ChurnFeatures[DaysSinceLastTransaction] <= 14, 4, ChurnFeatures[DaysSinceLastTransaction] <= 21, 5, 6 )' 'Int64'
    Ensure-CalcColumn 'ChurnFeatures' 'ActivityBin' 'SWITCH ( TRUE(), ChurnFeatures[EligibleForTraining] <> 1 || ISBLANK ( ChurnFeatures[AvgTransactionCount_6M] ), BLANK(), ChurnFeatures[AvgTransactionCount_6M] <= 1.5, "<= 1,5 Trans./Mon.", ChurnFeatures[AvgTransactionCount_6M] <= 3.0, "1,6-3,0 Trans./Mon.", ChurnFeatures[AvgTransactionCount_6M] <= 6.0, "3,1-6,0 Trans./Mon.", ChurnFeatures[AvgTransactionCount_6M] <= 10.0, "6,1-10,0 Trans./Mon.", "> 10,0 Trans./Mon." )' 'String'
    Ensure-CalcColumn 'ChurnFeatures' 'ActivityBinSort' 'SWITCH ( TRUE(), ChurnFeatures[EligibleForTraining] <> 1 || ISBLANK ( ChurnFeatures[AvgTransactionCount_6M] ), 99, ChurnFeatures[AvgTransactionCount_6M] <= 1.5, 1, ChurnFeatures[AvgTransactionCount_6M] <= 3.0, 2, ChurnFeatures[AvgTransactionCount_6M] <= 6.0, 3, ChurnFeatures[AvgTransactionCount_6M] <= 10.0, 4, 5 )' 'Int64'

    # Relationships for ChurnPredictions
    $rels = @(
        @{ Name = 'ChurnPredictions_customer_id_DimCustomer'; FromTbl = 'ChurnPredictions'; FromCol = 'customer_id'; ToTbl = 'DimCustomer'; ToCol = 'customer_id' },
        @{ Name = 'ChurnPredictions_Month_DimDate'; FromTbl = 'ChurnPredictions'; FromCol = 'Month'; ToTbl = 'DimDate'; ToCol = 'Date' }
    )
    foreach ($rel in $rels) {
        if (-not ($m.Relationships | Where-Object { $_.Name -eq $rel.Name })) {
            $r = New-Object "$T.SingleColumnRelationship"
            $r.Name = $rel.Name
            $r.FromColumn = $m.Tables[$rel.FromTbl].Columns[$rel.FromCol]
            $r.ToColumn = $m.Tables[$rel.ToTbl].Columns[$rel.ToCol]
            $r.FromCardinality = [Microsoft.AnalysisServices.Tabular.RelationshipEndCardinality]::Many
            $r.ToCardinality = [Microsoft.AnalysisServices.Tabular.RelationshipEndCardinality]::One
            $r.CrossFilteringBehavior = [Microsoft.AnalysisServices.Tabular.CrossFilteringBehavior]::OneDirection
            $m.Relationships.Add($r)
            Write-Output "RELATIONSHIP_ADDED: $($rel.Name)"
        }
    }

    # Helper DAX Calculated Tables
    function Ensure-CalcTable($tblName, $daxExpr) {
        if (-not $m.Tables.Contains($tblName)) {
            $tbl = New-Object "$T.Table"
            $tbl.Name = $tblName
            $p = New-Object "$T.Partition"
            $p.Name = $tblName
            $src = New-Object "$T.CalculatedPartitionSource"
            $src.Expression = $daxExpr
            $p.Source = $src
            $tbl.Partitions.Add($p)
            $m.Tables.Add($tbl)
            Write-Output "CALC_TABLE_ADDED: $tblName"
        } else {
            $m.Tables[$tblName].Partitions[0].Source.Expression = $daxExpr
        }
        $m.Tables[$tblName].RequestRefresh([Microsoft.AnalysisServices.Tabular.RefreshType]::Full)
    }

    Ensure-CalcTable 'DriverRankSlot' @'
DATATABLE (
    "DriverSlot", STRING,
    "SlotNumber", INTEGER,
    {
        { "1. Haupttreiber", 1 },
        { "2. Zweittreiber", 2 },
        { "3. Dritttreiber", 3 }
    }
)
'@

    Ensure-CalcTable 'CalibrationDeciles' @'
SUMMARIZECOLUMNS (
    ChurnPredictions[RiskDecile],
    FILTER ( ALL ( ChurnPredictions ), ChurnPredictions[ScoreType] = "Test (out-of-sample)" ),
    "Customers", COUNTROWS ( ChurnPredictions ),
    "MeanPredicted", AVERAGE ( ChurnPredictions[InactiveProbability] ),
    "ObservedRate", AVERAGE ( ChurnPredictions[ActualInactiveNextMonth] ),
    "DecileLabel", "Dezil " & FORMAT ( MIN ( ChurnPredictions[RiskDecile] ), "00" )
)
'@

    Ensure-CalcTable 'ConfusionMatrixTable' @'
DATATABLE (
    "MatrixCell", STRING,
    "ActualClass", STRING,
    "PredictedClass", STRING,
    "CustomerCount", INTEGER,
    "ShareOfTest", DOUBLE,
    "SortOrder", INTEGER,
    {
        { "True Negative (TN)", "Tatsächlich Aktiv (0)", "Prognose: Niedrig/Mittel (< 0,3179)", 29221, 0.7516, 1 },
        { "False Positive (FP)", "Tatsächlich Aktiv (0)", "Prognose: Hochrisiko (>= 0,3179)", 2325, 0.0598, 2 },
        { "False Negative (FN)", "Tatsächlich Inaktiv (1)", "Prognose: Niedrig/Mittel (< 0,3179)", 6143, 0.1580, 3 },
        { "True Positive (TP)", "Tatsächlich Inaktiv (1)", "Prognose: Hochrisiko (>= 0,3179)", 1189, 0.0306, 4 }
    }
)
'@

    Ensure-CalcTable 'ThresholdPolicyTable' @'
DATATABLE (
    "PolicyName", STRING,
    "RuleDescription", STRING,
    "ThresholdValue", DOUBLE,
    "FlaggedCustomers", INTEGER,
    "FlaggedShare", DOUBLE,
    "Precision", DOUBLE,
    "Recall", DOUBLE,
    "F1Score", DOUBLE,
    "Lift", DOUBLE,
    "SortOrder", INTEGER,
    {
        { "Top-5% Ranking (Kapazität)", "Exakte Top 5 % nach Risiko-Rang (Nov Test)", 0.3316, 1944, 0.0500, 0.3462, 0.0918, 0.1451, 1.84, 1 },
        { "Top-10% Ranking (Kapazitätsregel)", "Exakte Top 10 % nach Risiko-Rang (Nov Test)", 0.3179, 3888, 0.1000, 0.3369, 0.1786, 0.2335, 1.79, 2 },
        { "Operativer Schwellenwert (Validiert)", "Fester Cutoff p >= 0,3179 aus Okt-Validierung", 0.3179, 3514, 0.0904, 0.3384, 0.1622, 0.2193, 1.79, 3 },
        { "F1-Optimaler Schwellenwert", "Maximiert F1 auf Okt-Validierung (p >= 0,2553)", 0.2553, 12969, 0.3336, 0.3266, 0.5778, 0.4173, 1.73, 4 }
    }
)
'@

    Ensure-CalcTable 'DataQualityChecks' @'
DATATABLE (
    "CheckOrder", INTEGER,
    "Category", STRING,
    "CheckName", STRING,
    "MetricValue", STRING,
    "Status", STRING,
    "MethodologyNote", STRING,
    {
        { 1, "Rohdaten-Abstimmung", "Transaktionsanzahl (Rohdaten vs. ETL)", "3.159.157 = 3.159.157", "BESTANDEN", "100 % Übereinstimmung ohne Zeilenverlust; Duplikate als reale Transaktionen erhalten" },
        { 2, "Rohdaten-Abstimmung", "Transaktionsvolumen Gesamt (COP)", "100 % exakt abgestimmt", "BESTANDEN", "Keine Rundungsdifferenzen zwischen Roh-CSV und DuckDB-Parquet" },
        { 3, "Schlüsselintegrität", "Eindeutige Kunden (DimCustomer)", "48.723 Kunden (0 Duplikate)", "BESTANDEN", "Primärschlüssel customer_id vollständig und eindeutig" },
        { 4, "Schlüsselintegrität", "Verwaiste Transaktionsschlüssel (Orphans)", "0 verwaiste Schlüssel", "BESTANDEN", "Jede Transaktion ist einem validierten Kunden zugeordnet" },
        { 5, "Zeitreihen-Raster", "Kundenmonate (Jan-Dez 2023)", "569.706 Zeilen (0 Duplikate)", "BESTANDEN", "Vollständiges Kunden-Monats-Gitter ab erstem Beobachtungsmonat" },
        { 6, "Zeitreihen-Raster", "Monate ohne Transaktionen (InactiveMonth=1)", "101.985 Kundenmonate (17,9 %)", "BESTANDEN", "Explizit als 0-Transaktions-Monate im Raster modelliert" },
        { 7, "ML-Qualifizierung", "Trainingsfähige Beobachtungen (Jun-Nov)", "224.360 Zeilen (39.039 Positiv = 17,40 %)", "BESTANDEN", "Aktiv in T, >= 6 Monate Historie, Folgemonat T+1 beobachtet" },
        { 8, "Leakage-Schutz", "Ausschluss statisches Kundenprofil & Tenure", "61 reine Verhaltens-Features", "BESTANDEN", "Undatierter Profil-Snapshot & ObservedTenureMonths für ML gesperrt" },
        { 9, "Zieldefinition", "Transient-Inaktivitätsquote (Wiederaktivierung T+2)", "72,6 % in T+2 wieder aktiv", "HINWEIS", "Zielgröße misst Inaktivitätsrisiko im Folgemonat, keine Kontoauflösung" }
    }
)
'@

    $m.SaveChanges() | Out-Null
    Write-Output "PASS_2_CALC_COLS_AND_TABLES_SAVED"
} finally {
    $s.Disconnect()
}

# PASS 3: Configure SortByColumn and Add All DAX Measures
$s = New-Object "$T.Server"
$s.Connect("localhost:$port")
try {
    $m = $s.Databases[0].Model

    $cp = $m.Tables['ChurnPredictions']
    $cp.Columns['RiskLevel'].SortByColumn = $cp.Columns['RiskLevelSort']
    $cp.Columns['PriorityQuadrant'].SortByColumn = $cp.Columns['PriorityQuadrantSort']
    $cp.Columns['ValueSegment'].SortByColumn = $cp.Columns['ValueSegmentSort']
    $cp.Columns['RiskGroup2x2'].SortByColumn = $cp.Columns['RiskGroup2x2Sort']

    $cf = $m.Tables['ChurnFeatures']
    $cf.Columns['RecencyBin'].SortByColumn = $cf.Columns['RecencyBinSort']
    $cf.Columns['ActivityBin'].SortByColumn = $cf.Columns['ActivityBinSort']

    $dd = $m.Tables['DimDate']
    $dd.Columns['PipelinePhase'].SortByColumn = $dd.Columns['PipelinePhaseSort']

    $drs = $m.Tables['DriverRankSlot']
    $drs.Columns['DriverSlot'].SortByColumn = $drs.Columns['SlotNumber']

    $tp = $m.Tables['ThresholdPolicyTable']
    $tp.Columns['PolicyName'].SortByColumn = $tp.Columns['SortOrder']

    $cm = $m.Tables['ConfusionMatrixTable']
    $cm.Columns['MatrixCell'].SortByColumn = $cm.Columns['SortOrder']

    function Set-Measure($tableName, $measureName, $daxExpr, $formatString, $folder) {
        $tblObj = $m.Tables[$tableName]
        $existing = $tblObj.Measures | Where-Object { $_.Name -eq $measureName }
        if ($null -eq $existing) {
            $ms = New-Object "$T.Measure"
            $ms.Name = $measureName
            $ms.Expression = $daxExpr
            $ms.FormatString = $formatString
            $ms.DisplayFolder = $folder
            $tblObj.Measures.Add($ms)
        } else {
            $existing.Expression = $daxExpr
            $existing.FormatString = $formatString
            $existing.DisplayFolder = $folder
        }
    }

    # --- PAGE 1 & 2 MEASURES (on ChurnPredictions) ---
    Set-Measure 'ChurnPredictions' 'Bewertete aktive Kunden' 'DISTINCTCOUNT ( ChurnPredictions[customer_id] )' '#,0' '01 Management & Frühwarnsystem'
    Set-Measure 'ChurnPredictions' 'Bewertete aktive Kunden (Dez 2023)' 'CALCULATE ( DISTINCTCOUNT ( ChurnPredictions[customer_id] ), ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" )' '#,0' '01 Management & Frühwarnsystem'
    Set-Measure 'ChurnPredictions' 'Kunden mit hohem/kritischem Risiko' 'CALCULATE ( DISTINCTCOUNT ( ChurnPredictions[customer_id] ), ChurnPredictions[RiskLevel] IN { "Critical", "High" } )' '#,0' '01 Management & Frühwarnsystem'
    Set-Measure 'ChurnPredictions' 'Anteil Hoch-/Kritisch-Risiko' 'DIVIDE ( [Kunden mit hohem/kritischem Risiko], [Bewertete aktive Kunden] )' '0.00 %' '01 Management & Frühwarnsystem'
    Set-Measure 'ChurnPredictions' 'Kunden Top-10% Risiko-Rang' 'CALCULATE ( DISTINCTCOUNT ( ChurnPredictions[customer_id] ), ChurnPredictions[IsTop10PctRank] = 1 )' '#,0' '01 Management & Frühwarnsystem'
    Set-Measure 'ChurnPredictions' 'Werthaltige Risikokunden' 'CALCULATE ( DISTINCTCOUNT ( ChurnPredictions[customer_id] ), ChurnPredictions[PriorityQuadrant] = "High value + High risk" )' '#,0' '01 Management & Frühwarnsystem'
    Set-Measure 'ChurnPredictions' 'Durchschnittliches Inaktivitätsrisiko' 'AVERAGE ( ChurnPredictions[InactiveProbability] )' '0.00 %' '01 Management & Frühwarnsystem'
    Set-Measure 'ChurnPredictions' 'Transaktionsvolumen 3M Hochrisiko (COP)' 'CALCULATE ( SUM ( ChurnPredictions[TotalAmount_Recent3M] ), ChurnPredictions[RiskLevel] IN { "Critical", "High" } )' '"COP" #,0' '01 Management & Frühwarnsystem'
    Set-Measure 'ChurnPredictions' 'Transaktionsvolumen 3M Gefiltert (COP)' 'SUM ( ChurnPredictions[TotalAmount_Recent3M] )' '"COP" #,0' '01 Management & Frühwarnsystem'
    Set-Measure 'ChurnPredictions' 'Anteil Risikostufe' 'DIVIDE ( [Bewertete aktive Kunden], CALCULATE ( [Bewertete aktive Kunden], ALLSELECTED ( ChurnPredictions[RiskLevel], ChurnPredictions[RiskLevelSort] ) ) )' '0.0 %' '01 Management & Frühwarnsystem'
    Set-Measure 'ChurnPredictions' 'Durchschnittlicher Priority Score' 'AVERAGE ( ChurnPredictions[PriorityScore] )' '#,0' '01 Management & Frühwarnsystem'

    # Historical Observed Trend (Page 1 Chart C - ignores ScoreType filter on ChurnPredictions!)
    Set-Measure 'ChurnFeatures' 'Beobachtete Inaktivitätsquote (Historisch)' 'CALCULATE ( AVERAGE ( ChurnFeatures[InactiveNextMonth] ), ChurnFeatures[EligibleForTraining] = 1, REMOVEFILTERS ( ChurnPredictions ) )' '0.00 %' '01 Historischer Trend'
    Set-Measure 'ChurnFeatures' 'Qualifizierte Aktive Kunden (Historisch)' 'CALCULATE ( COUNTROWS ( ChurnFeatures ), ChurnFeatures[EligibleForTraining] = 1, REMOVEFILTERS ( ChurnPredictions ) )' '#,0' '01 Historischer Trend'

    # --- PAGE 3 MEASURES (03 Kundenprofil 360°) ---
    Set-Measure 'ChurnPredictions' 'Kunden-ID Auswahl' 'SELECTEDVALUE ( DimCustomer[customer_id], "Bitte Kunden auf Seite 2 auswählen" )' '' '03 Kundenprofil 360°'
    Set-Measure 'ChurnPredictions' 'Kunden Inaktivitätsrisiko (Dez 2023)' 'CALCULATE ( MAX ( ChurnPredictions[InactiveProbability] ), ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" )' '0.00 %' '03 Kundenprofil 360°'
    Set-Measure 'ChurnPredictions' 'Kunden Risiko-Rang (Dez 2023)' 'CALCULATE ( MAX ( ChurnPredictions[RiskRank] ), ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" )' '#,0' '03 Kundenprofil 360°'
    Set-Measure 'ChurnPredictions' 'Kunden Risikostufe (Dez 2023)' 'CALCULATE ( SELECTEDVALUE ( ChurnPredictions[RiskLevel], "-" ), ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" )' '' '03 Kundenprofil 360°'
    Set-Measure 'ChurnPredictions' 'Kunden Prioritätsquadrant (Dez 2023)' 'CALCULATE ( SELECTEDVALUE ( ChurnPredictions[PriorityQuadrant], "-" ), ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" )' '' '03 Kundenprofil 360°'
    Set-Measure 'ChurnPredictions' 'Kunden Tage seit letzter Transaktion (Dez 2023)' 'CALCULATE ( MAX ( ChurnPredictions[DaysSinceLastTransaction] ), ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" )' '#,0' '03 Kundenprofil 360°'
    Set-Measure 'ChurnFeatures' 'Kunden Transaktionen (Monat)' 'SUM ( ChurnFeatures[TransactionCount] )' '#,0' '03 Kundenprofil 360°'
    Set-Measure 'ChurnFeatures' 'Kunden Transaktionsvolumen (COP)' 'SUM ( ChurnFeatures[TotalAmount] )' '"COP" #,0' '03 Kundenprofil 360°'
    Set-Measure 'ChurnFeatures' 'Benchmark Aktive Kunden Transaktionen' 'CALCULATE ( AVERAGE ( ChurnFeatures[TransactionCount] ), ALL ( DimCustomer ), ChurnFeatures[TransactionCount] > 0 )' '0.00' '03 Kundenprofil 360°'
    Set-Measure 'ChurnPredictions' 'SHAP Treiber Name' 'VAR Slot = SELECTEDVALUE ( DriverRankSlot[SlotNumber] ) RETURN CALCULATE ( SWITCH ( Slot, 1, SELECTEDVALUE ( ChurnPredictions[TopDriver1] ), 2, SELECTEDVALUE ( ChurnPredictions[TopDriver2] ), 3, SELECTEDVALUE ( ChurnPredictions[TopDriver3] ) ), ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" )' '' '03 Kundenprofil 360°'
    Set-Measure 'ChurnPredictions' 'SHAP Treiber Wert' 'VAR Slot = SELECTEDVALUE ( DriverRankSlot[SlotNumber] ) RETURN CALCULATE ( SWITCH ( Slot, 1, MAX ( ChurnPredictions[TopDriver1Value] ), 2, MAX ( ChurnPredictions[TopDriver2Value] ), 3, MAX ( ChurnPredictions[TopDriver3Value] ) ), ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" )' '0.00' '03 Kundenprofil 360°'
    Set-Measure 'ChurnPredictions' 'SHAP Treiber Einfluss (Log-Odds)' 'VAR Slot = SELECTEDVALUE ( DriverRankSlot[SlotNumber] ) RETURN CALCULATE ( SWITCH ( Slot, 1, MAX ( ChurnPredictions[TopDriver1Impact] ), 2, MAX ( ChurnPredictions[TopDriver2Impact] ), 3, MAX ( ChurnPredictions[TopDriver3Impact] ) ), ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" )' '+0.000;-0.000;0.000' '03 Kundenprofil 360°'
    Set-Measure 'ChurnPredictions' 'SHAP Treiber Bezeichnung' 'VAR Slot = SELECTEDVALUE ( DriverRankSlot[SlotNumber] ) VAR Feat = [SHAP Treiber Name] VAR Val = [SHAP Treiber Wert] RETURN IF ( NOT ISBLANK ( Feat ), Slot & ". " & Feat & " (" & FORMAT ( Val, "0.##" ) & ")", BLANK() )' '' '03 Kundenprofil 360°'

    # --- PAGE 4 MEASURES (04 Risikotreiber & Verhaltensmuster) ---
    Set-Measure 'FeatureImportance' 'Globale SHAP Bedeutung (Test)' 'AVERAGE ( FeatureImportance[mean_abs_shap_test] )' '0.0000' '04 Risikotreiber (XAI)'
    Set-Measure 'FeatureImportance' 'Globale SHAP Bedeutung (Dez Scoring)' 'AVERAGE ( FeatureImportance[mean_abs_shap_scoring] )' '0.0000' '04 Risikotreiber (XAI)'
    Set-Measure 'FeatureImportance' 'SHAP Werte-Korrelation (Test)' 'AVERAGE ( FeatureImportance[value_shap_correlation_test] )' '+0.00;-0.00;0.00' '04 Risikotreiber (XAI)'
    Set-Measure 'ChurnFeatures' 'Beobachtete Inaktivitätsquote (Verhalten)' 'CALCULATE ( AVERAGE ( ChurnFeatures[InactiveNextMonth] ), ChurnFeatures[EligibleForTraining] = 1 )' '0.0 %' '04 Risikotreiber (XAI)'
    Set-Measure 'ChurnPredictions' 'Anteil Zahlungen (Payment %)' 'DIVIDE ( SUM ( ChurnPredictions[PaymentCount] ), SUM ( ChurnPredictions[TransactionCount] ) )' '0.0 %' '04 Transaktionsmix nach Risiko'
    Set-Measure 'ChurnPredictions' 'Anteil Überweisungen (Transfer %)' 'DIVIDE ( SUM ( ChurnPredictions[TransferCount] ), SUM ( ChurnPredictions[TransactionCount] ) )' '0.0 %' '04 Transaktionsmix nach Risiko'
    Set-Measure 'ChurnPredictions' 'Anteil Abhebungen (Withdrawal %)' 'DIVIDE ( SUM ( ChurnPredictions[WithdrawalCount] ), SUM ( ChurnPredictions[TransactionCount] ) )' '0.0 %' '04 Transaktionsmix nach Risiko'
    Set-Measure 'ChurnPredictions' 'Anteil Einzahlungen (Deposit %)' 'DIVIDE ( SUM ( ChurnPredictions[DepositCount] ), SUM ( ChurnPredictions[TransactionCount] ) )' '0.0 %' '04 Transaktionsmix nach Risiko'

    # --- PAGE 5 MEASURES (05 Modellgüte & Validierung) ---
    Set-Measure 'ChurnPredictions' 'Test ROC-AUC' '0.7405' '0.0000' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ChurnPredictions' 'Test PR-AUC' '0.3241' '0.0000' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ChurnPredictions' 'Test PR-AUC Baseline (Prävalenz)' '0.1886' '0.0000' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ChurnPredictions' 'Test Precision @ Top 10 %' '0.3369' '0.0 %' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ChurnPredictions' 'Test Recall @ Top 10 %' '0.1786' '0.0 %' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ChurnPredictions' 'Test Lift @ Top 10 %' '1.79' '0.00"x"' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ChurnPredictions' 'Test Brier Score' '0.1384' '0.0000' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ChurnPredictions' 'Test ECE (Kalibrierungsfehler)' '0.0152' '0.0000' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ModelExperiments' 'Validierungs-PR-AUC' 'AVERAGE ( ModelExperiments[val_pr_auc] )' '0.0000' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ModelExperiments' 'Validierungs-ROC-AUC' 'AVERAGE ( ModelExperiments[val_roc_auc] )' '0.0000' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'CalibrationDeciles' 'Kalibrierung Prognostiziertes Risiko' 'AVERAGE ( CalibrationDeciles[MeanPredicted] )' '0.0 %' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'CalibrationDeciles' 'Kalibrierung Beobachtete Inaktivität' 'AVERAGE ( CalibrationDeciles[ObservedRate] )' '0.0 %' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'CalibrationDeciles' 'Kalibrierung Ideallinie (45°)' 'AVERAGE ( CalibrationDeciles[MeanPredicted] )' '0.0 %' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ChurnPredictions' 'Test Beobachtete Inaktivitätsquote' 'CALCULATE ( AVERAGE ( ChurnPredictions[ActualInactiveNextMonth] ), ChurnPredictions[ScoreType] = "Test (out-of-sample)" )' '0.0 %' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ConfusionMatrixTable' 'Konfusionsmatrix Kundenanzahl' 'SUM ( ConfusionMatrixTable[CustomerCount] )' '#,0' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ConfusionMatrixTable' 'Konfusionsmatrix Anteil' 'AVERAGE ( ConfusionMatrixTable[ShareOfTest] )' '0.0 %' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ThresholdPolicyTable' 'Schwellenwert Precision' 'AVERAGE ( ThresholdPolicyTable[Precision] )' '0.0 %' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ThresholdPolicyTable' 'Schwellenwert Recall' 'AVERAGE ( ThresholdPolicyTable[Recall] )' '0.0 %' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ThresholdPolicyTable' 'Schwellenwert Flagged Share' 'AVERAGE ( ThresholdPolicyTable[FlaggedShare] )' '0.0 %' '05 Modellgüte (Nov 2023 Test)'
    Set-Measure 'ThresholdPolicyTable' 'Schwellenwert F1' 'AVERAGE ( ThresholdPolicyTable[F1Score] )' '0.000' '05 Modellgüte (Nov 2023 Test)'

    # --- PAGE 6 MEASURES (06 Datenqualität & Methodik) ---
    Set-Measure 'ChurnFeatures' 'Geprüfte Roh-Transaktionen' 'SUM ( ChurnFeatures[TransactionCount] )' '#,0' '06 Datenqualität & Governance'
    Set-Measure 'DimCustomer' 'Eindeutige Kunden Gesamt' 'COUNTROWS ( DimCustomer )' '#,0' '06 Datenqualität & Governance'
    Set-Measure 'ChurnFeatures' 'Kundenmonate Gesamt' 'COUNTROWS ( ChurnFeatures )' '#,0' '06 Datenqualität & Governance'
    Set-Measure 'ChurnFeatures' 'Monate ohne Transaktionen' 'CALCULATE ( COUNTROWS ( ChurnFeatures ), ChurnFeatures[TransactionCount] = 0 )' '#,0' '06 Datenqualität & Governance'
    Set-Measure 'ChurnFeatures' 'Aktive Kundenmonate' 'CALCULATE ( COUNTROWS ( ChurnFeatures ), ChurnFeatures[TransactionCount] > 0 )' '#,0' '06 Datenqualität & Governance'
    Set-Measure 'ChurnFeatures' 'Trainingsfähige Beobachtungen' 'CALCULATE ( COUNTROWS ( ChurnFeatures ), ChurnFeatures[EligibleForTraining] = 1 )' '#,0' '06 Datenqualität & Governance'
    Set-Measure 'ChurnFeatures' 'Verwaiste Schlüssel (Orphans)' '0' '#,0' '06 Datenqualität & Governance'

    $m.SaveChanges() | Out-Null
    Write-Output "PASS_3_SORT_AND_MEASURES_SAVED"

    # Export all measures to powerbi/dashboard_measures.dax for version control
    $daxLines = @("-- Auto-generated DAX catalog for the 6-page German IBCS Dashboard")
    foreach ($tblObj in $m.Tables) {
        foreach ($ms in $tblObj.Measures) {
            $daxLines += ""
            $daxLines += "-- Folder: $($ms.DisplayFolder) | Format: $($ms.FormatString)"
            $daxLines += "$($tblObj.Name)[$($ms.Name)] = $($ms.Expression)"
        }
    }
    [IO.File]::WriteAllText((Join-Path $root 'powerbi\dashboard_measures.dax'), ($daxLines -join "`r`n"), [Text.UTF8Encoding]::new($false))
    Write-Output "EXPORTED_DAX_CATALOG"

    # Also serialize powerbi/model.bim for version control
    $opts = New-Object "$T.SerializeOptions"
    $opts.IgnoreInferredObjects = $false
    $opts.IgnoreInferredProperties = $false
    $opts.IgnoreTimestamps = $true
    $bimJson = [Microsoft.AnalysisServices.Tabular.JsonSerializer]::SerializeDatabase($s.Databases[0], $opts)
    [IO.File]::WriteAllText((Join-Path $root 'powerbi\model.bim'), $bimJson, [Text.UTF8Encoding]::new($false))
    Write-Output "EXPORTED_MODEL_BIM ($($bimJson.Length) chars)"
} finally {
    $s.Disconnect()
}

# Run live DAX verification queries against localhost:$port via Microsoft.PowerBI.AdomdClient.dll
try {
    Add-Type -Path (Join-Path $PowerBIBin 'Microsoft.PowerBI.AdomdClient.dll')
    $conn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$port")
    $conn.Open()
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = @'
EVALUATE
ROW (
    "Dec_Active_Customers", [Bewertete aktive Kunden (Dez 2023)],
    "Dec_High_Crit", CALCULATE ( [Kunden mit hohem/kritischem Risiko], ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" ),
    "Dec_HighVal_HighRisk", CALCULATE ( [Werthaltige Risikokunden], ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" ),
    "Dec_Top10_Rank", CALCULATE ( [Kunden Top-10% Risiko-Rang], ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" ),
    "Dec_Avg_Prob", CALCULATE ( [Durchschnittliches Inaktivitätsrisiko], ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" ),
    "Dec_HighRisk_3M_COP", CALCULATE ( [Transaktionsvolumen 3M Hochrisiko (COP)], ChurnPredictions[ScoreType] = "Production (Dec 2023 -> Jan 2024)" ),
    "Hist_Inactivity_Rate", [Beobachtete Inaktivitätsquote (Historisch)],
    "Hist_Eligible_Rows", [Trainingsfähige Beobachtungen],
    "Raw_Tx_Count", [Geprüfte Roh-Transaktionen],
    "Total_Customers", [Eindeutige Kunden Gesamt],
    "Total_CustomerMonths", [Kundenmonate Gesamt],
    "Zero_Tx_Months", [Monate ohne Transaktionen]
)
'@
    $reader = $cmd.ExecuteReader()
    if ($reader.Read()) {
        for ($i = 0; $i -lt $reader.FieldCount; $i++) {
            Write-Output ("DAX_VERIFY: " + $reader.GetName($i) + " = " + $reader.GetValue($i))
        }
    }
    $reader.Close()
    $conn.Close()
} catch {
    Write-Output "DAX_VERIFY_ERROR: $($_.Exception.Message)"
}

# Inspect Power BI Desktop window and save the open PBIX
Start-Sleep -Seconds 5
$beforeWrite = (Get-Item $pbix).LastWriteTime
$pbiProc = Get-Process PBIDesktop -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if ($null -ne $pbiProc) {
    Write-Output "PBIDesktop MainWindowTitle: '$($pbiProc.MainWindowTitle)'"
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    $rootEl = [System.Windows.Automation.AutomationElement]::FromHandle($pbiProc.MainWindowHandle)
    $btnCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
    $btns = $rootEl.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
    $btnNames = @()
    foreach ($b in $btns) {
        $n = $b.Current.Name
        if (-not [string]::IsNullOrWhiteSpace($n)) { $btnNames += $n }
        if ($n -eq 'Save' -or $n -eq 'Speichern') {
            $inv = $null
            if ($b.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$inv)) {
                $inv.Invoke()
                Write-Output "INVOKED_UIA_SAVE_BUTTON: $n"
            }
        }
    }
    Write-Output ("Visible UIA Buttons: " + (($btnNames | Select-Object -First 25) -join ' | '))

    $wshell = New-Object -ComObject WScript.Shell
    [void]$wshell.AppActivate($pbiProc.Id)
    Start-Sleep -Seconds 2
    $wshell.SendKeys('^s')
    for ($w = 0; $w -lt 15; $w++) {
        Start-Sleep -Seconds 2
        $afterWrite = (Get-Item $pbix).LastWriteTime
        if ($afterWrite -gt $beforeWrite) {
            Write-Output "PBIX_SAVED_ON_DISK: $($afterWrite.ToString('o'))"
            break
        }
    }
}


