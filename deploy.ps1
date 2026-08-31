# =============================================================================
# deploy.ps1 — Deploy task-management to all 3 clusters
#
# Usage (PowerShell):
#   .\deploy.ps1              # Deploy to all 3 clusters (dev -> staging -> prod)
#   .\deploy.ps1 dev          # Deploy only to dev
#   .\deploy.ps1 staging      # Deploy only to staging
#   .\deploy.ps1 prod         # Deploy only to prod
#   .\deploy.ps1 clean        # Remove from all clusters
#   .\deploy.ps1 clean dev    # Remove only from dev
#   .\deploy.ps1 status       # Show status of all clusters
# =============================================================================

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$chartDir = Join-Path $scriptDir "helm"
$logFile = Join-Path $scriptDir "deploy.log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    $logEntry | Tee-Object -FilePath $logFile -Append | Out-Null

    $color = switch ($Level) {
        "INFO"    { "Green" }
        "WARN"    { "Yellow" }
        "ERROR"   { "Red" }
        default    { "White" }
    }
    Write-Host $logEntry -ForegroundColor $color
}

function Write-Info { Write-Log $args[0] "INFO" }
function Write-Warn { Write-Log $args[0] "WARN" }
function Write-Error { Write-Log $args[0] "ERROR" }

function Test-Command {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Check-Prerequisites {
    $missing = @()
    foreach ($cmd in @("kubectl", "helm", "docker")) {
        if (-not (Test-Command $cmd)) {
            $missing += $cmd
        }
    }
    if ($missing.Count -gt 0) {
        Write-Error "Missing prerequisites: $($missing -join ', ')"
        Write-Host "Please install: $($missing -join ', ')" -ForegroundColor Red
        exit 1
    }
}

function Build-Images {
    Write-Info "Building Docker images..."
    Set-Location $scriptDir
    docker compose build task-service notification-service web-ui
    Write-Info "Docker images built successfully"
}

function Deploy-To {
    param([string]$Env)

    $releaseName = "task-management-$Env"
    $namespace = "task-management-$Env"
    $valuesFile = Join-Path $chartDir "values-$Env.yaml"

    if (-not (Test-Path $valuesFile)) {
        Write-Error "Values file not found: $valuesFile"
        return
    }

    Write-Info ("=" * 60)
    Write-Info "Deploying to $Env cluster"
    Write-Info ("=" * 60)

    # Select the correct kubectl context
    $context = "k8s-$Env"
    $contexts = kubectl config get-contexts -o name 2>$null
    if ($contexts -contains $context) {
        Write-Info "Using kubectl context: $context"
        kubectl config use-context $context 2>$null | Out-Null
    } else {
        Write-Warn "Context '$context' not found, using current context"
    }

    # Create namespace if it doesn't exist
    $nsExists = kubectl get namespace $namespace 2>$null
    if (-not $nsExists) {
        Write-Info "Creating namespace: $namespace"
        kubectl create namespace $namespace --dry-run=client -o yaml | kubectl apply -f - 2>$null
    }

    # Check if release already exists
    $releaseExists = helm list -n $namespace -q 2>$null | Select-String -Pattern "^$releaseName$"
    if ($releaseExists) {
        Write-Info "Upgrading existing release: $releaseName"
        helm upgrade $releaseName $chartDir `
            --namespace $namespace `
            --values $valuesFile `
            --wait `
            --timeout 300s `
            --atomic `
            --recreate-pods 2>&1 | Out-Null
    } else {
        Write-Info "Installing new release: $releaseName"
        helm install $releaseName $chartDir `
            --namespace $namespace `
            --values $valuesFile `
            --create-namespace `
            --wait `
            --timeout 300s `
            --atomic `
            --recreate-pods 2>&1 | Out-Null
    }

    # Wait for pods
    Write-Info "Waiting for pods to be ready..."
    $pods = kubectl get pods -n $namespace -l release=$releaseName -o name 2>$null
    if ($pods) {
        Write-Info "Pod status:"
        kubectl get pods -n $namespace -l release=$releaseName -o wide
    }

    Write-Info "$Env deployment completed!"
}

function Clean-From {
    param([string]$Env)

    $releaseName = "task-management-$Env"
    $namespace = "task-management-$Env"

    Write-Info "Cleaning up $Env cluster..."

    $context = "k8s-$Env"
    $contexts = kubectl config get-contexts -o name 2>$null
    if ($contexts -contains $context) {
        kubectl config use-context $context 2>$null | Out-Null
    }

    helm uninstall $releaseName -n $namespace 2>$null
    kubectl delete namespace $namespace 2>$null

    Write-Info "$Env cleanup completed!"
}

# Main
Check-Prerequisites

$command = $args[0]
$subCommand = $args[1]

switch ($command) {
    "dev" {
        Build-Images
        Deploy-To "dev"
    }
    "staging" {
        Build-Images
        Deploy-To "staging"
    }
    "prod" {
        Build-Images
        Deploy-To "prod"
    }
    "all" {
        Build-Images
        Deploy-To "dev"
        Deploy-To "staging"
        Deploy-To "prod"
        Write-Info ("=" * 60)
        Write-Info "All deployments completed!"
        Write-Info ("=" * 60)
    }
    "clean" {
        if ($subCommand -eq "all" -or -not $subCommand) {
            Clean-From "dev"
            Clean-From "staging"
            Clean-From "prod"
        } else {
            Clean-From $subCommand
        }
    }
    "status" {
        foreach ($env in @("dev", "staging", "prod")) {
            $namespace = "task-management-$env"
            Write-Info "=== $env ==="
            $ns = kubectl get ns $namespace 2>$null
            if ($ns) {
                kubectl get pods -n $namespace
            } else {
                Write-Warn "Namespace $namespace not found"
            }
            Write-Host ""
        }
    }
    default {
        Write-Host @"
Usage: .\deploy.ps1 {dev|staging|prod|all|clean|status}

Commands:
  dev        - Deploy to dev cluster
  staging    - Deploy to staging cluster
  prod       - Deploy to prod cluster
  all        - Deploy to all 3 clusters
  clean      - Remove from all clusters
  clean <env> - Remove from specific cluster
  status     - Show status of all clusters
"@
        exit 1
    }
}
