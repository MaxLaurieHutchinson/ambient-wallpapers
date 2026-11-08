$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot '..\scripts\windows_wallpaper.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }

# Extract and execute just the pure role resolver. This leaves COM, registry,
# display state, and wallpaper files untouched in this synthetic contract test.
$functionAst = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Resolve-WallpaperDisplayRole'
}, $true)
if ($null -eq $functionAst) { throw 'Could not find Resolve-WallpaperDisplayRole.' }
. ([scriptblock]::Create($functionAst.Extent.Text))

$wideLaptop = [pscustomobject]@{ DevicePath='SYNTHETIC-LAPTOP'; Width=3840; Height=2160 }
$tallExternal = [pscustomobject]@{ DevicePath='SYNTHETIC-EXTERNAL'; Width=2400; Height=1600 }
$roles = @{
    'SYNTHETIC-LAPTOP'='laptop'
    'SYNTHETIC-EXTERNAL'='monitor'
}
$resolvedLaptop = Resolve-WallpaperDisplayRole -Monitor $wideLaptop -DisplayRoles $roles
$resolvedExternal = Resolve-WallpaperDisplayRole -Monitor $tallExternal -DisplayRoles $roles
if ($resolvedLaptop.Role -ne 'laptop' -or $resolvedLaptop.Source -ne 'explicit') {
    throw 'An explicitly mapped 16:9 laptop was not honored.'
}
if ($resolvedExternal.Role -ne 'monitor' -or $resolvedExternal.Source -ne 'explicit') {
    throw 'An explicitly mapped 3:2 external monitor was not honored.'
}
$defaultLaptop = Resolve-WallpaperDisplayRole -Monitor $tallExternal
$defaultMonitor = Resolve-WallpaperDisplayRole -Monitor $wideLaptop
if ($defaultLaptop.Role -ne 'laptop' -or $defaultLaptop.Source -ne 'heuristic') { throw 'The default 3:2 laptop heuristic changed.' }
if ($defaultMonitor.Role -ne 'monitor' -or $defaultMonitor.Source -ne 'heuristic') { throw 'The default wide-monitor heuristic changed.' }
'Synthetic display-role tests passed (explicit mapping and aspect-ratio fallback).'
