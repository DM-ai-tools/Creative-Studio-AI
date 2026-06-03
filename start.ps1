param(
    [ValidateSet("setup", "backend", "frontend", "docker")]
    [string]$Mode = "backend"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

switch ($Mode) {
    "setup" {
        npm run setup
    }
    "frontend" {
        npm run start:frontend
    }
    "docker" {
        npm run docker:up
    }
    default {
        npm run start:backend
    }
}
