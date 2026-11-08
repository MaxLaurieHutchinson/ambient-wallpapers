$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot '..\scripts\install_signal_task.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $scriptPath), [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | ForEach-Object { $_.ToString() } | Out-String) }

# Import only pure planner/formatting functions from the script AST. This keeps
# the contract test independent of Task Scheduler and any OS wallpaper state.
$pureFunctions = @('Get-DefaultTaskName', 'Get-SignalsJobActionArguments', 'Get-TaskPlan')
foreach ($name in $pureFunctions) {
    $functionAst = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name }, $true)
    if (-not $functionAst) { throw "Pure helper missing: $name" }
    . ([scriptblock]::Create($functionAst.Extent.Text))
}

$taskFolder = '\AmbientWallpapers\'
$base = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) 'ambient-wallpaper-contract'))
$profile = Join-Path $base 'private profile.json'
$python = Join-Path $base 'pythonw.exe'
$runner = Join-Path $base 'signals_job.py'

$nameA = Get-DefaultTaskName -AbsoluteProfilePath $profile
$nameB = Get-DefaultTaskName -AbsoluteProfilePath $profile.ToUpperInvariant()
if ($nameA -ne $nameB -or $nameA -notmatch '^AmbientWallpapers-[0-9a-f]{16}$') { throw 'Task name is not deterministic for a case-insensitive profile path.' }

$arguments = Get-SignalsJobActionArguments -RunnerPath $runner -AbsoluteProfilePath $profile
if ($arguments -ne ('"{0}" --profile "{1}"' -f $runner, $profile)) { throw 'Action command line does not quote the signal job and profile paths.' }

$plan = Get-TaskPlan -AbsoluteProfilePath $profile -AbsolutePythonPath $python -AbsoluteRunnerPath $runner `
    -ResolvedTaskName $nameA -EveryMinutes 15 -CurrentIdentity 'TEST\SyntheticUser'
if ($plan.action.execute -ne $python -or $plan.action.arguments -notmatch ' --profile ') { throw 'Plan action shape is wrong.' }
if ($plan.interval_minutes -ne 15 -or $plan.triggers.Count -ne 2 -or $plan.triggers[1] -notmatch 'repeats indefinitely every 15 minutes') { throw 'Plan trigger shape is wrong.' }
if ($plan.principal.logon_type -ne 'Interactive' -or $plan.principal.run_level -ne 'Limited') { throw 'Plan principal is not interactive and limited.' }
if ($plan.settings.multiple_instances -ne 'IgnoreNew' -or -not $plan.settings.allow_start_on_battery -or -not $plan.settings.continue_on_battery -or $plan.settings.wake_to_run -or $plan.settings.execution_time_limit_minutes -ne 5) { throw 'Plan settings do not meet the local-task contract.' }
if (-not $plan.install_allowed) { throw 'New task should be installable.' }

$collision = Get-TaskPlan -AbsoluteProfilePath $profile -AbsolutePythonPath $python -AbsoluteRunnerPath $runner `
    -ResolvedTaskName $nameA -EveryMinutes 15 -CurrentIdentity 'TEST\SyntheticUser' -TaskExists $true
if ($collision.install_allowed) { throw 'Existing task must block install without explicit replacement.' }
$replacement = Get-TaskPlan -AbsoluteProfilePath $profile -AbsolutePythonPath $python -AbsoluteRunnerPath $runner `
    -ResolvedTaskName $nameA -EveryMinutes 15 -CurrentIdentity 'TEST\SyntheticUser' -TaskExists $true -AllowReplace $true
if (-not $replacement.install_allowed) { throw 'Explicit replacement should unblock the exact task.' }

'SIGNAL_TASK_SYNTHETIC_CONTRACT_OK'
