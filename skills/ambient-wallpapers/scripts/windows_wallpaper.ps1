[CmdletBinding()]
param(
    [ValidateSet('Inspect', 'Plan', 'Apply', 'Restore')]
    [string] $Mode = 'Inspect',
    [string] $ImagePath,
    [string] $LaptopImagePath,
    [string[]] $MonitorImagePaths,
    [string] $AssignmentPath,
    [string] $StatePath,
    [string] $BackupRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# IDesktopWallpaper method order/signatures follow the Windows SDK IDL in
# shobjidl_core.h. Microsoft documents these methods as Windows 8+ APIs.
if (-not ('WallpaperNative.IDesktopWallpaper' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

namespace WallpaperNative {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    public enum DESKTOP_WALLPAPER_POSITION : int {
        CENTER = 0, TILE = 1, STRETCH = 2, FIT = 3, FILL = 4, SPAN = 5
    }

    [ComImport]
    [Guid("B92B56A9-8B55-4E14-9A89-0199BBB6F93B")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IDesktopWallpaper {
        void SetWallpaper([MarshalAs(UnmanagedType.LPWStr)] string monitorID,
                          [MarshalAs(UnmanagedType.LPWStr)] string wallpaper);
        [return: MarshalAs(UnmanagedType.LPWStr)]
        string GetWallpaper([MarshalAs(UnmanagedType.LPWStr)] string monitorID);
        [return: MarshalAs(UnmanagedType.LPWStr)]
        string GetMonitorDevicePathAt(uint monitorIndex);
        uint GetMonitorDevicePathCount();
        RECT GetMonitorRECT([MarshalAs(UnmanagedType.LPWStr)] string monitorID);
        void SetBackgroundColor(uint color);
        uint GetBackgroundColor();
        void SetPosition(DESKTOP_WALLPAPER_POSITION position);
        DESKTOP_WALLPAPER_POSITION GetPosition();
    }

    // Keep the IUnknown interface cast inside C#: PowerShell's -as operator
    // does not expose this non-IDispatch COM interface reliably.
    public sealed class Client {
        private readonly IDesktopWallpaper api;
        public Client() {
            var clsid = new Guid("C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD");
            api = (IDesktopWallpaper)Activator.CreateInstance(Type.GetTypeFromCLSID(clsid));
        }
        public void SetWallpaper(string id, string path) { api.SetWallpaper(id, path); }
        public string GetWallpaper(string id) { return api.GetWallpaper(id); }
        public string GetMonitorDevicePathAt(uint index) { return api.GetMonitorDevicePathAt(index); }
        public uint GetMonitorDevicePathCount() { return api.GetMonitorDevicePathCount(); }
        public RECT GetMonitorRECT(string id) { return api.GetMonitorRECT(id); }
        public void SetPosition(DESKTOP_WALLPAPER_POSITION position) { api.SetPosition(position); }
        public DESKTOP_WALLPAPER_POSITION GetPosition() { return api.GetPosition(); }
    }
}
'@
}

$wallpaper = [WallpaperNative.Client]::new()

function Get-RegistryValueRecord {
    param([Microsoft.Win32.RegistryHive] $Hive, [string] $SubKey, [string] $Name)
    $key = [Microsoft.Win32.RegistryKey]::OpenBaseKey($Hive, [Microsoft.Win32.RegistryView]::Default)
    try {
        $child = $key.OpenSubKey($SubKey, $false)
        if ($null -eq $child -or $child.GetValueNames() -notcontains $Name) {
            return [pscustomobject]@{ Hive=$Hive.ToString(); SubKey=$SubKey; Name=$Name; Present=$false; Kind=$null; Value=$null }
        }
        $kind = $child.GetValueKind($Name).ToString()
        $value = $child.GetValue($Name, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        return [pscustomobject]@{ Hive=$Hive.ToString(); SubKey=$SubKey; Name=$Name; Present=$true; Kind=$kind; Value=$value }
    } finally { $key.Dispose() }
}

function Restore-RegistryValueRecord {
    param($Record)
    $hive = [Enum]::Parse([Microsoft.Win32.RegistryHive], [string]$Record.Hive)
    $key = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, [Microsoft.Win32.RegistryView]::Default)
    try {
        $child = $key.OpenSubKey([string]$Record.SubKey, $true)
        if ($null -eq $child) { $child = $key.CreateSubKey([string]$Record.SubKey, $true) }
        try {
            if (-not [bool]$Record.Present) {
                $child.DeleteValue([string]$Record.Name, $false)
                return
            }
            $kind = [Enum]::Parse([Microsoft.Win32.RegistryValueKind], [string]$Record.Kind)
            $value = switch ($kind) {
                'DWord'       { [int]$Record.Value; break }
                'QWord'       { [long]$Record.Value; break }
                'String'      { [string]$Record.Value; break }
                'ExpandString'{ [string]$Record.Value; break }
                default       { throw "Registry value kind '$kind' is not supported for wallpaper restore." }
            }
            $child.SetValue([string]$Record.Name, $value, $kind)
        } finally { $child.Dispose() }
    } finally { $key.Dispose() }
}

function Get-DesktopSnapshot {
    $count = $wallpaper.GetMonitorDevicePathCount()
    $monitors = @()
    for ($i = 0; $i -lt $count; $i++) {
        $id = $wallpaper.GetMonitorDevicePathAt([uint32]$i)
        $rect = $wallpaper.GetMonitorRECT($id)
        $path = $wallpaper.GetWallpaper($id)
        $monitors += [pscustomobject]@{
            Index = $i; DevicePath = $id; WallpaperPath = $path
            Left = $rect.Left; Top = $rect.Top; Right = $rect.Right; Bottom = $rect.Bottom
            Width = ($rect.Right - $rect.Left); Height = ($rect.Bottom - $rect.Top)
            Connected = (($rect.Right - $rect.Left) -gt 0 -and ($rect.Bottom - $rect.Top) -gt 0)
        }
    }
    $style = Get-RegistryValueRecord -Hive CurrentUser -SubKey 'Control Panel\Desktop' -Name 'WallpaperStyle'
    $tile = Get-RegistryValueRecord -Hive CurrentUser -SubKey 'Control Panel\Desktop' -Name 'TileWallpaper'
    $backgroundType = Get-RegistryValueRecord -Hive CurrentUser -SubKey 'Software\Microsoft\Windows\CurrentVersion\Explorer\Wallpapers' -Name 'BackgroundType'
    [pscustomobject]@{
        Position = $wallpaper.GetPosition().ToString()
        PositionValue = [int]$wallpaper.GetPosition()
        Monitors = @($monitors)
        Registry = [pscustomobject]@{ BackgroundType=$backgroundType; WallpaperStyle=$style; TileWallpaper=$tile }
    }
}

function Save-WallpaperState {
    param($Snapshot)
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $backupDir = Join-Path ([IO.Path]::GetFullPath($BackupRoot)) $stamp
    [void](New-Item -ItemType Directory -Path $backupDir -Force)
    $copies = @{}
    foreach ($monitor in $Snapshot.Monitors) {
        $source = [string]$monitor.WallpaperPath
        if ([string]::IsNullOrWhiteSpace($source) -or -not (Test-Path -LiteralPath $source -PathType Leaf)) { continue }
        $key = [IO.Path]::GetFullPath($source)
        if (-not $copies.ContainsKey($key)) {
            $leaf = [IO.Path]::GetFileName($source)
            $dest = Join-Path $backupDir ('original-{0}-{1}' -f $copies.Count, $leaf)
            Copy-Item -LiteralPath $source -Destination $dest
            $copies[$key] = $dest
        }
        $monitor | Add-Member -NotePropertyName BackupPath -NotePropertyValue $copies[$key] -Force
    }
    $state = [pscustomobject]@{
        SchemaVersion = 1
        CreatedAt = (Get-Date).ToString('o')
        RestoreNote = if ($Snapshot.Registry.BackgroundType.Present -and [string]$Snapshot.Registry.BackgroundType.Value -eq '3') {
            'Original mode was Windows Spotlight. A backed-up static image can be restored, but Spotlight reactivation is not verified; use Windows Settings to re-enable Spotlight and verify it.'
        } else { $null }
        Position = $Snapshot.Position
        PositionValue = $Snapshot.PositionValue
        Monitors = @($Snapshot.Monitors)
        Registry = $Snapshot.Registry
        BackupDirectory = $backupDir
    }
    if ([string]::IsNullOrWhiteSpace($StatePath)) { $StatePath = Join-Path $backupDir 'wallpaper-state.json' }
    $stateFullPath = [IO.Path]::GetFullPath($StatePath)
    $stateParent = Split-Path -Parent $stateFullPath
    if (-not (Test-Path -LiteralPath $stateParent -PathType Container)) { [void](New-Item -ItemType Directory -Path $stateParent -Force) }
    $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $stateFullPath -Encoding UTF8
    return $stateFullPath
}

function Get-SelectedImagePaths {
    $selectedLaptop = $LaptopImagePath
    $selectedMonitors = @($MonitorImagePaths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $selectedRoles = @{}
    if (-not [string]::IsNullOrWhiteSpace($AssignmentPath)) {
        $manifestFile = (Resolve-Path -LiteralPath $AssignmentPath -ErrorAction Stop).Path
        $manifest = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
        if ($null -eq $manifest.PSObject.Properties['laptop'] -or $manifest.laptop -isnot [string]) {
            throw "Assignment JSON must have a string 'laptop' path: $manifestFile"
        }
        if ($null -eq $manifest.PSObject.Properties['monitors'] -or $manifest.monitors -is [string]) {
            throw "Assignment JSON must have a 'monitors' array: $manifestFile"
        }
        $selectedLaptop = [string]$manifest.laptop
        $selectedMonitors = @($manifest.monitors | ForEach-Object {
            if ($_ -isnot [string] -or [string]::IsNullOrWhiteSpace($_)) {
                throw "Each entry in assignment JSON 'monitors' must be a non-empty path string: $manifestFile"
            }
            [string]$_
        })
        if (-not [IO.Path]::IsPathRooted($selectedLaptop)) {
            throw "Assignment JSON laptop path must be absolute: '$selectedLaptop'"
        }
        foreach ($monitorImage in $selectedMonitors) {
            if (-not [IO.Path]::IsPathRooted([string]$monitorImage)) {
                throw "Assignment JSON monitor paths must be absolute: '$monitorImage'"
            }
        }
        if ($null -ne $manifest.PSObject.Properties['display_roles']) {
            $roleDocument = $manifest.display_roles
            if ($null -eq $roleDocument -or $roleDocument -is [array] -or $roleDocument -is [string]) {
                throw "Assignment JSON 'display_roles' must be an object mapping display device paths to 'laptop' or 'monitor'."
            }
            foreach ($property in $roleDocument.PSObject.Properties) {
                $devicePath = [string]$property.Name
                $roleValue = $property.Value
                if ([string]::IsNullOrWhiteSpace($devicePath) -or $roleValue -isnot [string] -or
                    [string]::IsNullOrWhiteSpace([string]$roleValue) -or
                    ([string]$roleValue).ToLowerInvariant() -notin @('laptop', 'monitor')) {
                    throw "Assignment JSON display_roles must contain non-empty device paths mapped to 'laptop' or 'monitor'. Invalid entry: '$devicePath'."
                }
                $selectedRoles[$devicePath] = ([string]$roleValue).ToLowerInvariant()
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($selectedLaptop) -and -not [string]::IsNullOrWhiteSpace($ImagePath)) {
        $selectedLaptop = $ImagePath
    }
    return [pscustomobject]@{ Laptop=$selectedLaptop; Monitors=@($selectedMonitors); DisplayRoles=$selectedRoles }
}

function Resolve-WallpaperDisplayRole {
    param(
        [Parameter(Mandatory)] $Monitor,
        [System.Collections.IDictionary] $DisplayRoles = @{}
    )
    $devicePath = [string]$Monitor.DevicePath
    if ($DisplayRoles.Contains($devicePath)) {
        $role = [string]$DisplayRoles[$devicePath]
        if ($role -notin @('laptop', 'monitor')) { throw "Unsupported role '$role' for display '$devicePath'." }
        return [pscustomobject]@{ Role=$role; Source='explicit' }
    }
    $ratio = [double]$Monitor.Width / [double]$Monitor.Height
    $role = if ([Math]::Abs($ratio - 1.5) -le 0.12) { 'laptop' } else { 'monitor' }
    return [pscustomobject]@{ Role=$role; Source='heuristic' }
}

function Get-WallpaperAssignments {
    param($Snapshot, $Images)
    $connected = @($Snapshot.Monitors | Where-Object Connected | Sort-Object Left, Top)
    if ($connected.Count -eq 0) { throw 'No connected monitors were returned by IDesktopWallpaper.' }
    $assignments = @()
    $externalIndex = 0
    foreach ($monitor in $connected) {
        $displayRole = Resolve-WallpaperDisplayRole -Monitor $monitor -DisplayRoles $Images.DisplayRoles
        $isLaptop = $displayRole.Role -eq 'laptop'
        if ($isLaptop -and -not [string]::IsNullOrWhiteSpace([string]$Images.Laptop)) {
            $chosen = [string]$Images.Laptop
        } elseif (-not $isLaptop -and @($Images.Monitors).Count -gt 0) {
            $chosen = [string]$Images.Monitors[$externalIndex % @($Images.Monitors).Count]
            $externalIndex++
        } elseif (-not [string]::IsNullOrWhiteSpace($ImagePath)) {
            $chosen = $ImagePath
        } else {
            $chosen = [string]$Images.Laptop
        }
        if ([string]::IsNullOrWhiteSpace($chosen)) {
            throw "No image selected for connected display ($($monitor.Width)x$($monitor.Height)). Supply -ImagePath or the per-display paths."
        }
        $resolved = (Resolve-Path -LiteralPath $chosen -ErrorAction Stop).Path
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) { throw "Image path is not a file: $resolved" }
        $assignments += [pscustomobject]@{
            DevicePath=$monitor.DevicePath; WallpaperPath=$resolved; Role=$displayRole.Role; RoleSource=$displayRole.Source
            Width=$monitor.Width; Height=$monitor.Height; Left=$monitor.Left
        }
    }
    return $assignments
}

function Wait-WallpaperReadback {
    param(
        [object[]] $Expected,
        [ValidateSet('WallpaperPath', 'BackupPath')]
        [string] $PathProperty = 'WallpaperPath',
        [ValidateRange(1, 30000)]
        [int] $TimeoutMilliseconds = 5000
    )
    $clock = [Diagnostics.Stopwatch]::StartNew()
    do {
        $pending = @($Expected | Where-Object {
            $expectedPath = [string]$_.$PathProperty
            [string]::IsNullOrWhiteSpace($expectedPath) -or
                $wallpaper.GetWallpaper([string]$_.DevicePath) -ne $expectedPath
        })
        if ($pending.Count -eq 0) { return $true }
        $remaining = $TimeoutMilliseconds - [int]$clock.ElapsedMilliseconds
        if ($remaining -le 0) { break }
        [System.Threading.Thread]::Sleep([Math]::Min(250, $remaining))
    } while ($clock.ElapsedMilliseconds -lt $TimeoutMilliseconds)
    return $false
}

if ($Mode -eq 'Inspect') {
    Get-DesktopSnapshot | ConvertTo-Json -Depth 8
    return
}

if ($Mode -eq 'Plan' -or $Mode -eq 'Apply') {
    if ($Mode -eq 'Apply' -and [string]::IsNullOrWhiteSpace($BackupRoot)) {
        throw 'Apply requires -BackupRoot so rollback data has an explicit destination.'
    }
    $snapshot = Get-DesktopSnapshot
    $images = Get-SelectedImagePaths
    $assignments = @(Get-WallpaperAssignments -Snapshot $snapshot -Images $images)

    if ($Mode -eq 'Plan') {
        [pscustomobject]@{
            Result = 'Planned'
            Position = 'FILL'
            Assignment = @($assignments)
            DisconnectedMonitorCount = @($snapshot.Monitors | Where-Object { -not $_.Connected }).Count
            SettingsChanged = $false
            BackupCreated = $false
        } | ConvertTo-Json -Depth 6
        return
    }

    $connected = @($snapshot.Monitors | Where-Object Connected)
    foreach ($monitor in $connected) {
        if ([string]::IsNullOrWhiteSpace([string]$monitor.WallpaperPath) -or -not (Test-Path -LiteralPath $monitor.WallpaperPath -PathType Leaf)) {
            throw "Cannot create a complete rollback copy for connected monitor '$($monitor.DevicePath)' because its current wallpaper image path is empty or unavailable. No desktop changes were made."
        }
    }

    # Persist rollback metadata and byte-for-byte copies of available originals before touching desktop state.
    $stateFullPath = Save-WallpaperState -Snapshot $snapshot
    $backupState = Get-Content -LiteralPath $stateFullPath -Raw | ConvertFrom-Json
    foreach ($monitor in $connected) {
        $saved = @($backupState.Monitors | Where-Object { $_.DevicePath -eq $monitor.DevicePath })[0]
        $savedFile = [string]$saved.BackupPath
        if ([string]::IsNullOrWhiteSpace($savedFile) -or -not (Test-Path -LiteralPath $savedFile -PathType Leaf)) {
            throw "Backup is missing for connected display '$($monitor.DevicePath)'. No desktop changes were made."
        }
    }

    $mutationStarted = $false
    try {
        $mutationStarted = $true
        # Keep static wallpapers from being replaced by the previous Spotlight mode.
        $pictureModeKey = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Software\Microsoft\Windows\CurrentVersion\Explorer\Wallpapers')
        try { $pictureModeKey.SetValue('BackgroundType', 0, [Microsoft.Win32.RegistryValueKind]::DWord) }
        finally { $pictureModeKey.Dispose() }
        if (@($assignments | Select-Object -ExpandProperty WallpaperPath -Unique).Count -eq 1) {
            $wallpaper.SetWallpaper($null, $assignments[0].WallpaperPath)
        } else {
            foreach ($assignment in $assignments) { $wallpaper.SetWallpaper($assignment.DevicePath, $assignment.WallpaperPath) }
        }
        $wallpaper.SetPosition([WallpaperNative.DESKTOP_WALLPAPER_POSITION]::FILL)
        # Explorer processes wallpaper changes asynchronously. Verify its read-back.
        if (-not (Wait-WallpaperReadback -Expected $assignments) -or
            $wallpaper.GetPosition() -ne [WallpaperNative.DESKTOP_WALLPAPER_POSITION]::FILL) {
            throw 'Windows did not confirm every requested wallpaper and Fill position within five seconds.'
        }
    } catch {
        $applyError = $_.Exception.Message
        $rollbackError = $null
        if ($mutationStarted) {
            try {
                foreach ($saved in $backupState.Monitors | Where-Object Connected) {
                    $wallpaper.SetWallpaper([string]$saved.DevicePath, [string]$saved.BackupPath)
                }
                $wallpaper.SetPosition([WallpaperNative.DESKTOP_WALLPAPER_POSITION][int]$backupState.PositionValue)
                foreach ($record in @($backupState.Registry.BackgroundType, $backupState.Registry.WallpaperStyle, $backupState.Registry.TileWallpaper)) {
                    Restore-RegistryValueRecord -Record $record
                }
                $savedConnected = @($backupState.Monitors | Where-Object Connected)
                if (-not (Wait-WallpaperReadback -Expected $savedConnected -PathProperty BackupPath) -or
                    $wallpaper.GetPosition() -ne [WallpaperNative.DESKTOP_WALLPAPER_POSITION][int]$backupState.PositionValue) {
                    throw 'Windows did not confirm the original wallpapers and display position.'
                }
            } catch { $rollbackError = $_.Exception.Message }
        }
        if ($rollbackError) { throw "$applyError Rollback also failed: $rollbackError. Saved rollback data: $stateFullPath" }
        throw "$applyError The original display settings were restored from: $stateFullPath"
    }
    [pscustomobject]@{
        Result = 'Applied'; StatePath = $stateFullPath; Position = 'FILL'
        Assignment = @($assignments)
        DisconnectedMonitorCount = @($snapshot.Monitors | Where-Object { -not $_.Connected }).Count
        OriginalSpotlightCaveat = $snapshot.Registry.BackgroundType.Present -and [string]$snapshot.Registry.BackgroundType.Value -eq '3'
    } | ConvertTo-Json -Depth 6
    return
}

if ($Mode -eq 'Restore') {
    if ([string]::IsNullOrWhiteSpace($StatePath) -or -not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { throw 'Restore requires -StatePath pointing to an Apply state JSON file.' }
    $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    if ([int]$state.SchemaVersion -ne 1) { throw "Unsupported wallpaper state schema: $($state.SchemaVersion)" }
    $current = Get-DesktopSnapshot
    $connectedIds = @($current.Monitors | Where-Object Connected | ForEach-Object DevicePath)
    $restoreItems = @($state.Monitors | Where-Object Connected)
    foreach ($item in $restoreItems) {
        if ($connectedIds -notcontains [string]$item.DevicePath) { throw "Saved monitor is not currently connected: $($item.DevicePath). Reconnect it before restoring to avoid a partial restore." }
        if ([string]::IsNullOrWhiteSpace([string]$item.BackupPath) -or -not (Test-Path -LiteralPath $item.BackupPath -PathType Leaf)) { throw "No verified backup file exists for monitor '$($item.DevicePath)'; refusing partial restore." }
    }
    foreach ($item in $restoreItems) {
        $wallpaper.SetWallpaper([string]$item.DevicePath, [string]$item.BackupPath)
    }
    $position = [WallpaperNative.DESKTOP_WALLPAPER_POSITION][int]$state.PositionValue
    $wallpaper.SetPosition($position)
    foreach ($record in @($state.Registry.BackgroundType, $state.Registry.WallpaperStyle, $state.Registry.TileWallpaper)) {
        Restore-RegistryValueRecord -Record $record
    }
    $restorePosition = [WallpaperNative.DESKTOP_WALLPAPER_POSITION][int]$state.PositionValue
    if (-not (Wait-WallpaperReadback -Expected $restoreItems -PathProperty BackupPath) -or
        $wallpaper.GetPosition() -ne $restorePosition) {
        throw "Windows did not confirm the restored wallpapers and display position within five seconds. State file: $StatePath"
    }
    $spotlight = $state.Registry.BackgroundType.Present -and [string]$state.Registry.BackgroundType.Value -eq '3'
    [pscustomobject]@{
        Result = if ($spotlight) { 'StaticSnapshotRestored_SpotlightUnverified' } else { 'Restored' }
        StatePath = [IO.Path]::GetFullPath($StatePath)
        Position = $state.Position
        SpotlightReactivationVerified = $false
        RestoreNote = $state.RestoreNote
    } | ConvertTo-Json -Depth 5
}
