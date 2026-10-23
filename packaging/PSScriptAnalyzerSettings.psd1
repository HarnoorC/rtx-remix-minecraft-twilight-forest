# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# PSScriptAnalyzer waivers for packaging/installer.ps1.
# Run with:
#   Invoke-ScriptAnalyzer -Path packaging/installer.ps1 `
#     -Settings packaging/PSScriptAnalyzerSettings.psd1 `
#     -Severity Warning,Error
#
# Each ExcludeRules entry must be accompanied by a justification below so
# future reviewers can evaluate whether the waiver still applies.
@{
    ExcludeRules = @(
        # Installer is a user-facing TUI. Write-Host is the correct way to
        # render colored, interactive terminal output; Write-Output /
        # Write-Information produce pipeline objects that don't render as
        # ANSI-styled text and can't be positioned with cursor ops.
        'PSAvoidUsingWriteHost'

        # This script is an end-user installer, not a reusable module.
        # Destructive operations gate on our own Confirm-YesNo / the
        # -AcknowledgeDataLoss flag. Adding SupportsShouldProcess plumbing
        # for -WhatIf / -Confirm on every Remove-* helper would add
        # significant boilerplate without changing behavior for end users.
        'PSUseShouldProcessForStateChangingFunctions'

        # Plural nouns are semantically correct for the functions flagged:
        # Sync-JvmArgs acts on a JvmArgs line which is a single VALUE that's
        # grammatically plural (multiple flags), Install-ModFiles copies
        # multiple files as a unit, Remove-ModArtifacts removes multiple
        # artifacts, etc. Renaming to singular (Sync-JvmArg / Install-ModFile)
        # would be misleading about what the function does.
        'PSUseSingularNouns'
    )
}
