# Run spend pipeline for Company A and Company B
$DataRoot = if ($env:CANTILL_DATA_ROOT) { $env:CANTILL_DATA_ROOT } else { "data/Cantill_DataML_Task_Kit" }

Write-Host "Running Company A pipeline..." -ForegroundColor Cyan
python -m spend_pipeline --config configs/company_a.yaml --data-root $DataRoot --output outputs/vaibhav__A.csv --diagnostics outputs/A_diagnostics.json

Write-Host "Running Company B pipeline..." -ForegroundColor Cyan
python -m spend_pipeline --config configs/company_b.yaml --data-root $DataRoot --output outputs/vaibhav__B.csv --diagnostics outputs/B_diagnostics.json

Write-Host "Pipeline runs completed successfully." -ForegroundColor Green

