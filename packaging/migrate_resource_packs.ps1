# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

param(
    [Parameter(Mandatory)] [string]$McDir,
    [Parameter(Mandatory)]
    [ValidateSet('RtxRemix-LabPBR', 'rtx-remix', 'rtx-remix-labpbr')]
    [string]$LegacyPackName
)

$ErrorActionPreference = 'Stop'

function Remove-LegacyResourcePack {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    if ((Get-Item -LiteralPath $Path).Attributes -band [IO.FileAttributes]::ReparsePoint) { return $false }
    if (Test-Path -LiteralPath (Join-Path $Path '.rtx-remix-world-pack')) { return $false }
    $metadataPath = Join-Path $Path 'pack.mcmeta'
    # The name alone is not ownership: world-local and user packs may reuse it.
    if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $Path 'BLOCK_TEXTURES.txt') -PathType Leaf)) { return $false }
    try {
        $metadata = [IO.File]::ReadAllText($metadataPath) | ConvertFrom-Json
    } catch [ArgumentException] {
        return $false
    }
    if ((ConvertTo-Json -InputObject $metadata -Compress -Depth 10) -cne
        '{"pack":{"pack_format":34,"description":"RTX Remix LabPBR Development Pack"}}') { return $false }
    Remove-Item -LiteralPath $Path -Recurse -Force
    Write-Host "Removed retired baseline resource pack: $Path"
    return $true
}

function Update-ResourcePackOptions {
    param([string]$Path, [string]$LegacyPackName, [bool]$RemoveLegacyEntry)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    $text = [IO.File]::ReadAllText($Path)
    $match = [regex]::Match($text, '(?m)^resourcePacks:[^\r\n]*')
    $packs = if ($match.Success) { @($match.Value.Substring('resourcePacks:'.Length) | ConvertFrom-Json) } else { @() }
    $ordered = @('vanilla', 'fabric') + @($packs | Where-Object {
        $_ -cne 'vanilla' -and $_ -cne 'fabric' -and
        (-not $RemoveLegacyEntry -or $_ -cne "file/$LegacyPackName")
    })
    $line = 'resourcePacks:' + (ConvertTo-Json -InputObject $ordered -Compress)
    if ($match.Success) {
        $updated = $text.Remove($match.Index, $match.Length).Insert($match.Index, $line)
    } else {
        $newline = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
        $separator = if ($text.Length -gt 0 -and -not $text.EndsWith("`n")) { $newline } else { '' }
        $updated = $text + $separator + $line + $newline
    }
    if ($updated -ceq $text) { return }
    $bytes = [IO.File]::ReadAllBytes($Path)
    $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191
    $temporary = "$Path.tmp-$([guid]::NewGuid().ToString('N'))"
    try {
        [IO.File]::WriteAllText($temporary, $updated, [Text.UTF8Encoding]::new($bom))
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

$legacyPack = Join-Path $McDir "resourcepacks\$LegacyPackName"
$removed = Remove-LegacyResourcePack -Path $legacyPack
Update-ResourcePackOptions -Path (Join-Path $McDir 'options.txt') -LegacyPackName $LegacyPackName -RemoveLegacyEntry $removed
