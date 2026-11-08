[CmdletBinding()]
param(
    [ValidateSet('Plan', 'Install', 'Inspect', 'Remove')]
    [string]$Mode = 'Plan',

    [Parameter(Mandatory = $true)]
    [string]$ProfilePath,

    [string]$PythonPath,

    [ValidatePattern('^[A-Za-z0-9_.-]{1,100}$')]
    [string]$TaskName,

    [ValidateRange(1, 1440)]
    [int]$IntervalMinutes = 15,

    [switch]$Replace
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$taskFolder = '\AmbientWallpapers\'

function Resolve-ExistingFile {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Label)
    if (-not [IO.Path]::IsPathRooted($Path)) {
        throw "$Label must be an absolute path."
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label does not exist: $Path"
    }
    return [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Path).Path)
}

function Get-DefaultTaskName {
    param([Parameter(Mandatory)][string]$AbsoluteProfilePath)
    $normalized = [IO.Path]::GetFullPath($AbsoluteProfilePath).ToLowerInvariant()
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($normalized)
        $hash = ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace '-', '').Substring(0, 16).ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
    return "AmbientWallpapers-$hash"
}

function Get-SignalsJobActionArguments {
    param(
        [Parameter(Mandatory)][string]$RunnerPath,
        [Parameter(Mandatory)][string]$AbsoluteProfilePath
    )
    # Windows paths cannot contain a double quote. Pass the executable separately
    # as the task action's Execute field, so only profile/script paths need quoting.
    if ($RunnerPath.Contains('"') -or $AbsoluteProfilePath.Contains('"')) {
        throw 'Windows executable and profile paths cannot contain a double quote.'
    }
    return '"{0}" --profile "{1}"' -f $RunnerPath, $AbsoluteProfilePath
}

function Get-TaskPlan {
    param(
        [Parameter(Mandatory)][string]$AbsoluteProfilePath,
        [Parameter(Mandatory)][string]$AbsolutePythonPath,
        [Parameter(Mandatory)][string]$AbsoluteRunnerPath,
        [Parameter(Mandatory)][string]$ResolvedTaskName,
        [Parameter(Mandatory)][int]$EveryMinutes,
        [Parameter(Mandatory)][string]$CurrentIdentity,
        [bool]$TaskExists = $false,
        [bool]$AllowReplace = $false
    )
    $arguments = Get-SignalsJobActionArguments -RunnerPath $AbsoluteRunnerPath -AbsoluteProfilePath $AbsoluteProfilePath
    [pscustomobject]@{
        mode = 'Plan'
        task_path = $taskFolder
        task_name = $ResolvedTaskName
        exists = $TaskExists
        replace = $AllowReplace
        install_allowed = (-not $TaskExists) -or $AllowReplace
        interval_minutes = $EveryMinutes
        action = [pscustomobject]@{
            execute = $AbsolutePythonPath
            arguments = $arguments
            working_directory = [IO.Path]::GetDirectoryName($AbsoluteRunnerPath)
        }
        principal = [pscustomobject]@{
            user = $CurrentIdentity
            logon_type = 'Interactive'
            run_level = 'Limited'
        }
        triggers = @('AtLogOn for current user', "Initial time trigger in one minute, then repeats indefinitely every $EveryMinutes minutes")
        settings = [pscustomobject]@{
            multiple_instances = 'IgnoreNew'
            start_when_available = $true
            allow_start_on_battery = $true
            continue_on_battery = $true
            wake_to_run = $false
            execution_time_limit_minutes = 5
        }
    }
}

function Read-EnabledProfile {
    param([Parameter(Mandatory)][string]$AbsoluteProfilePath)
    try {
        $config = Get-Content -LiteralPath $AbsoluteProfilePath -Raw | ConvertFrom-Json
    }
    catch {
        throw "Could not read profile JSON: $($_.Exception.Message)"
    }
    if ($config.enabled -isnot [bool] -or -not $config.enabled) {
        throw 'Profile must have enabled=true before the signal task can be installed.'
    }
    if ($config.allow_apply -isnot [bool] -or -not $config.allow_apply) {
        throw 'Profile must have allow_apply=true before the signal task can be installed.'
    }
    return $config
}

function Get-ExactTask {
    param([Parameter(Mandatory)][string]$Name)
    return Get-ScheduledTask -TaskPath $taskFolder -TaskName $Name -ErrorAction SilentlyContinue
}

function Get-ActionDefinition {
    param([Parameter(Mandatory)][string]$AbsolutePythonPath, [Parameter(Mandatory)][string]$AbsoluteRunnerPath, [Parameter(Mandatory)][string]$AbsoluteProfilePath)
    New-ScheduledTaskAction -Execute $AbsolutePythonPath `
        -Argument (Get-SignalsJobActionArguments -RunnerPath $AbsoluteRunnerPath -AbsoluteProfilePath $AbsoluteProfilePath) `
        -WorkingDirectory ([IO.Path]::GetDirectoryName($AbsoluteRunnerPath))
}

function Get-TriggerDefinitions {
    param([Parameter(Mandatory)][int]$EveryMinutes, [Parameter(Mandatory)][string]$CurrentIdentity)
    # The ScheduledTasks cmdlet accepts repetition settings on its Once trigger
    # set. Omitting RepetitionDuration means repeat indefinitely (Task Scheduler
    # schema), avoiding a null Repetition object on Daily triggers.
    $periodic = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) `
        -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
    $logon = New-ScheduledTaskTrigger -AtLogOn -User $CurrentIdentity
    return @($periodic, $logon)
}

function Get-SettingsDefinition {
    $settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    $settings.WakeToRun = $false
    return $settings
}

function Ensure-TaskFolder {
    # Register-ScheduledTask can register into a task folder only after that
    # folder exists. Keep creation inside explicit Install mode.
    $service = New-Object -ComObject 'Schedule.Service'
    $service.Connect()
    $folderPath = $taskFolder.TrimEnd('\')
    try {
        $null = $service.GetFolder($folderPath)
    }
    catch {
        $null = $service.GetFolder('\').CreateFolder('AmbientWallpapers', $null)
    }
    $null = $service.GetFolder($folderPath)
}

$profileAbsolute = Resolve-ExistingFile -Path $ProfilePath -Label 'ProfilePath'
$scriptAbsolute = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'signals_job.py'))
if (-not (Test-Path -LiteralPath $scriptAbsolute -PathType Leaf)) {
    throw "The signal job was not found beside this script: $scriptAbsolute"
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$resolvedName = if ($TaskName) { $TaskName } else { Get-DefaultTaskName -AbsoluteProfilePath $profileAbsolute }

if ($Mode -in @('Plan', 'Install')) {
    if (-not $PythonPath) { throw 'PythonPath is required for Plan and Install.' }
    $pythonAbsolute = Resolve-ExistingFile -Path $PythonPath -Label 'PythonPath'
    if ($Mode -eq 'Install') { $null = Read-EnabledProfile -AbsoluteProfilePath $profileAbsolute }
    $existing = Get-ExactTask -Name $resolvedName
    $plan = Get-TaskPlan -AbsoluteProfilePath $profileAbsolute -AbsolutePythonPath $pythonAbsolute `
        -AbsoluteRunnerPath $scriptAbsolute -ResolvedTaskName $resolvedName -EveryMinutes $IntervalMinutes `
        -CurrentIdentity $identity -TaskExists ([bool]$existing) -AllowReplace ([bool]$Replace)

    if ($Mode -eq 'Plan') {
        $plan.mode = 'Plan'
        if ($existing -and -not $Replace) { $plan | Add-Member -NotePropertyName blocked_reason -NotePropertyValue 'Task already exists; pass -Replace to replace this exact task.' }
        $plan | ConvertTo-Json -Depth 8
        return
    }

    if ($existing -and -not $Replace) {
        throw "Task '$taskFolder$resolvedName' already exists. Pass -Replace to replace this exact task."
    }
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
    $action = Get-ActionDefinition -AbsolutePythonPath $pythonAbsolute -AbsoluteRunnerPath $scriptAbsolute -AbsoluteProfilePath $profileAbsolute
    $triggers = Get-TriggerDefinitions -EveryMinutes $IntervalMinutes -CurrentIdentity $identity
    $settings = Get-SettingsDefinition
    Ensure-TaskFolder
    $null = Register-ScheduledTask -TaskPath $taskFolder -TaskName $resolvedName -Action $action `
        -Trigger $triggers -Principal $principal -Settings $settings -Description 'Update cached wallpaper signals and select an approved ambient wallpaper.' -Force:$Replace
    $registered = Get-ExactTask -Name $resolvedName
    if (-not $registered) { throw 'Task registration returned without a readable task; installation is unconfirmed.' }
    [pscustomobject]@{ mode = 'Install'; status = 'registered'; task_path = $taskFolder; task_name = $resolvedName; state = [string]$registered.State } | ConvertTo-Json -Depth 4
    return
}

if ($Mode -eq 'Inspect') {
    $task = Get-ExactTask -Name $resolvedName
    if (-not $task) {
        [pscustomobject]@{ mode = 'Inspect'; status = 'not_found'; task_path = $taskFolder; task_name = $resolvedName } | ConvertTo-Json -Depth 5
        return
    }
    $info = Get-ScheduledTaskInfo -TaskPath $taskFolder -TaskName $resolvedName
    [pscustomobject]@{ mode = 'Inspect'; status = 'found'; task_path = $taskFolder; task_name = $resolvedName; state = [string]$task.State; actions = @($task.Actions); triggers = @($task.Triggers); principal = $task.Principal; settings = $task.Settings; last_run_time = $info.LastRunTime; last_task_result = $info.LastTaskResult; next_run_time = $info.NextRunTime } | ConvertTo-Json -Depth 8
    return
}

if ($Mode -eq 'Remove') {
    $task = Get-ExactTask -Name $resolvedName
    if (-not $task) {
        [pscustomobject]@{ mode = 'Remove'; status = 'not_found'; task_path = $taskFolder; task_name = $resolvedName } | ConvertTo-Json -Depth 4
        return
    }
    Unregister-ScheduledTask -TaskPath $taskFolder -TaskName $resolvedName -Confirm:$false
    $remaining = Get-ExactTask -Name $resolvedName
    if ($remaining) { throw 'Task removal could not be verified.' }
    [pscustomobject]@{ mode = 'Remove'; status = 'removed'; task_path = $taskFolder; task_name = $resolvedName } | ConvertTo-Json -Depth 4
}
