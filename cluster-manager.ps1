<#
.SYNOPSIS
    Cluster Manager - PowerShell management script for a Kubernetes cluster
    with 3 environments (dev, staging, prod).

.DESCRIPTION
    Manages minikube, namespaces, deployments, services, and more.
    Run with: .\cluster-manager.ps1 <command> [args...]

.NOTES
    Author: DevOps Team
    Version: 1.0
#>

#Requires -Version 5.1

# ============================================================
# Configuration
# ============================================================

$ScriptName = "cluster-manager"
$ScriptVersion = "1.0"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Base directory for manifests and backups
$BaseDir = $ScriptDir
$BackupDir = Join-Path $BaseDir "backups"
$ManifestDir = Join-Path $BaseDir "manifests"

# Minikube path
$MinikubePath = "C:\Program Files\Kubernetes\Minikube\minikube.exe"

# Helm path - check winget install location
function Get-HelmPath {
    $locations = @(
        "C:\Program Files\Helm\helm.exe",
        "C:\Program Files (x86)\Helm\helm.exe",
        (Join-Path $env:LOCALAPPDATA "Programs\Helm\helm.exe"),
        (Join-Path $env:ProgramFiles "Helm\helm.exe"),
        (Join-Path $env:ProgramFiles(x86) "Helm\helm.exe")
    )
    foreach ($loc in $locations) {
        if (Test-Path $loc) {
            return $loc
        }
    }
    # Fallback: check PATH
    $helmInPath = Get-Command helm.exe -ErrorAction SilentlyContinue
    if ($helmInPath) {
        return $helmInPath.Source
    }
    return $null
}
$HelmPath = Get-HelmPath

# Environments and namespaces
$Environments = @("dev", "staging", "prod")
$Namespaces = @{
    dev      = "task-management-dev"
    staging  = "task-management-staging"
    prod     = "task-management-prod"
}

# Services per namespace
$Services = @(
    @{ Name = "task-service"; Port = 8000; ContainerPort = 8000 }
    @{ Name = "notification-service"; Port = 9000; ContainerPort = 9000 }
    @{ Name = "web-ui"; Port = 5000; ContainerPort = 5000 }
    @{ Name = "db"; Port = 5432; ContainerPort = 5432 }
)

# Docker image base
$DockerImageBase = "docker.io/library/devops_practice"

# ============================================================
# Color output helpers
# ============================================================

function Write-Color {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::White
    )
    Write-Host $Message -ForegroundColor $Color
}

function Write-Success {
    param([string]$Message)
    Write-Host "  [SUCCESS] $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "  [ERROR] $Message" -ForegroundColor Red
}

function Write-Warning {
    param([string]$Message)
    Write-Host "  [WARNING] $Message" -ForegroundColor Yellow
}

function Write-Info {
    param([string]$Message)
    Write-Host "  [INFO] $Message" -ForegroundColor Cyan
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Box {
    param([string]$Text, [ConsoleColor]$Color = [ConsoleColor]::White)
    Write-Host ""
    Write-Host "  +------------------------------------------+" -ForegroundColor $Color
    Write-Host "  | $Text" -ForegroundColor $Color
    Write-Host "  +------------------------------------------+" -ForegroundColor $Color
    Write-Host ""
}

# ============================================================
# Utility functions
# ============================================================

function Test-Command {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-DockerRunning {
    $dockerInfo = docker info 2>&1 | Out-String
    return $LASTEXITCODE -eq 0
}

function Test-MinikubeRunning {
    try {
        $status = & $MinikubePath status -o json 2>&1 | ConvertFrom-Json
        return $status.MachineProfile.Status -eq "Running"
    }
    catch {
        return $false
    }
}

function Get-CurrentNamespace {
    param([string]$Env)
    return $Namespaces[$Env]
}

function Get-ImageName {
    param([string]$Service)
    return "$DockerImageBase-$Service:latest"
}

function Get-DeploymentName {
    param([string]$Service)
    return $Service
}

function Ensure-KubectlContext {
    & $MinikubePath kubectl -- config use-context minikube 2>&1 | Out-Null
}

function Ensure-Namespace {
    param([string]$Namespace)
    $exists = kubectl get namespace $Namespace 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        kubectl create namespace $Namespace 2>&1 | Out-Null
        Write-Info "Created namespace: $Namespace"
    }
}

function Test-DockerImageExists {
    param([string]$Image)
    $imageCheck = docker image inspect $Image 2>&1 | Out-Null
    return $LASTEXITCODE -eq 0
}

function Get-Timestamp {
    return Get-Date -Format "yyyyMMdd_HHmmss"
}

function Get-BackupFileName {
    param([string]$Env)
    return "backup_${Env}_$(Get-Timestamp).tar.gz"
}

# ============================================================
# Command: start
# ============================================================

function Start-Cluster {
    Write-Section "Starting Minikube Cluster"

    if (Test-MinikubeRunning) {
        Write-Success "Minikube is already running."
        return
    }

    Write-Info "Starting minikube..."
    & $MinikubePath start --driver=docker --memory=4096 --cpus=4 2>&1 | ForEach-Object {
        Write-Host "    $_"
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Minikube started successfully."
        Ensure-KubectlContext
        Write-Success "Kubectl context set to minikube."

        # Ensure all namespaces exist
        foreach ($env in $Environments) {
            Ensure-Namespace -Namespace $Namespaces[$env]
        }
        Write-Success "All namespaces verified."
    }
    else {
        Write-Error "Failed to start minikube."
        exit 1
    }
}

# ============================================================
# Command: stop
# ============================================================

function Stop-Cluster {
    Write-Section "Stopping Minikube Cluster"

    if (-not (Test-MinikubeRunning)) {
        Write-Warning "Minikube is not running."
        return
    }

    Write-Info "Stopping minikube..."
    & $MinikubePath stop 2>&1 | ForEach-Object {
        Write-Host "    $_"
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Minikube stopped successfully."
    }
    else {
        Write-Error "Failed to stop minikube."
    }
}

# ============================================================
# Command: status
# ============================================================

function Show-Status {
    Write-Section "Cluster Status - All Environments"

    foreach ($env in $Environments) {
        $ns = $Namespaces[$env]
        Write-Host ""
        Write-Host "  Environment: $env" -ForegroundColor Yellow
        Write-Host "  Namespace: $ns" -ForegroundColor Yellow
        Write-Host "  $(('-' * 50))" -ForegroundColor Gray

        # Check if namespace exists
        $nsExists = kubectl get namespace $ns 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    Namespace '$ns' does not exist." -ForegroundColor DarkGray
            Write-Host ""
            continue
        }

        # Get pods in a table format
        $pods = kubectl get pods -n $ns -o wide --no-headers 2>&1
        if ($LASTEXITCODE -eq 0 -and $pods) {
            # Display header
            Write-Host "  POD NAME                              STATUS    RESTARTS   AGE   IP             NODE" -ForegroundColor Gray
            Write-Host "  $(('-' * 60))" -ForegroundColor Gray

            $lines = $pods | Where-Object { $_.Trim() }
            foreach ($line in $lines) {
                $parts = $line -split '\s+'
                if ($parts.Count -ge 7) {
                    $name = $parts[0].PadRight(35)
                    $status = $parts[1].PadRight(8)
                    $restarts = $parts[2].PadRight(10)
                    $age = $parts[3].PadRight(10)
                    $ip = $parts[5].PadRight(15)
                    $node = $parts[6]

                    # Color code status
                    $statusColor = [ConsoleColor]::White
                    if ($status -eq "Running") { $statusColor = [ConsoleColor]::Green }
                    elseif ($status -eq "Pending" -or $status -eq "ContainerCreating") { $statusColor = [ConsoleColor]::Yellow }
                    elseif ($status -eq "Error" -or $status -eq "CrashLoopBackOff") { $statusColor = [ConsoleColor]::Red }
                    elseif ($status -eq "ImagePullBackOff" -or $status -eq "ErrImagePull") { $statusColor = [ConsoleColor]::Red }
                    elseif ($status -eq "Completed" -or $status -eq "Succeeded") { $statusColor = [ConsoleColor]::Green }

                    Write-Host "    $name $status $restarts $age $ip $node" -ForegroundColor $statusColor
                }
                else {
                    Write-Host "    $line" -ForegroundColor DarkGray
                }
            }
        }
        else {
            Write-Host "    No pods found or error querying." -ForegroundColor DarkGray
        }

        # Show services
        Write-Host ""
        Write-Host "  Services:" -ForegroundColor Gray
        $svcs = kubectl get svc -n $ns --no-headers 2>&1
        if ($LASTEXITCODE -eq 0 -and $svcs) {
            $svcLines = $svcs | Where-Object { $_.Trim() }
            foreach ($svc in $svcLines) {
                Write-Host "    $svc" -ForegroundColor DarkCyan
            }
        }

        Write-Host ""
    }

    # Cluster overview
    Write-Section "Cluster Overview"
    if (Test-MinikubeRunning) {
        Write-Success "Minikube: Running"
    }
    else {
        Write-Error "Minikube: Stopped"
    }

    $nodeInfo = kubectl get nodes -o wide --no-headers 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Nodes:" -ForegroundColor Gray
        foreach ($line in $nodeInfo) {
            if ($line.Trim()) {
                Write-Host "    $line" -ForegroundColor DarkGray
            }
        }
    }

    $memInfo = kubectl top nodes 2>&1
    if ($LASTEXITCODE -eq 0 -and $memInfo) {
        Write-Host ""
        Write-Host "  Resource Usage:" -ForegroundColor Gray
        foreach ($line in $memInfo) {
            if ($line.Trim()) {
                Write-Host "    $line" -ForegroundColor DarkGray
            }
        }
    }
}

# ============================================================
# Command: logs
# ============================================================

function Show-Logs {
    param([string]$Env, [string]$Service)

    if (-not $Namespaces.ContainsKey($Env)) {
        Write-Error "Invalid environment: '$Env'. Valid environments: $($Environments -join ', ')"
        return
    }

    $ns = $Namespaces[$Env]
    $deployName = Get-DeploymentName -Service $Service

    Write-Section "Logs - Environment: $env | Service: $Service"

    # Check namespace
    $nsExists = kubectl get namespace $ns 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Namespace '$ns' does not exist. Deploy first."
        return
    }

    # Get pod name
    $pods = kubectl get pods -n $ns -l app=$deployName --no-headers 2>&1
    if ($LASTEXITCODE -ne 0 -or -not $pods) {
        Write-Warning "No pods found for deployment '$deployName' in namespace '$ns'."
        return
    }

    $podName = ($pods | Where-Object { $_.Trim() })[0] -split '\s+' | Select-Object -First 1
    if (-not $podName) {
        Write-Error "Could not determine pod name for deployment '$deployName'."
        return
    }

    Write-Info "Showing logs for pod: $podName (deployment: $deployName)"
    Write-Host ""

    kubectl logs -n $ns $podName --tail=100 --follow 2>&1 | ForEach-Object {
        Write-Host "  $_"
    }
}

# ============================================================
# Command: deploy
# ============================================================

function Deploy-All {
    Write-Section "Deploying to All Environments"

    # Step 1: Start minikube if not running
    if (-not (Test-MinikubeRunning)) {
        Write-Info "Starting minikube..."
        & $MinikubePath start --driver=docker --memory=4096 --cpus=4 2>&1 | ForEach-Object {
            Write-Host "    $_"
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to start minikube. Aborting deploy."
            exit 1
        }
        Write-Success "Minikube started."
    }

    Ensure-KubectlContext

    # Step 2: Build Docker images
    Write-Section "Building Docker Images"
    foreach ($service in $Services) {
        $imageName = Get-ImageName -Service $service.Name
        $buildPath = Join-Path $BaseDir $service.Name
        $dockerfilePath = Join-Path $buildPath "Dockerfile"

        if (Test-Path $dockerfilePath) {
            Write-Info "Building image: $imageName"
            docker build -t $imageName -f $dockerfilePath $buildPath 2>&1 | ForEach-Object {
                Write-Host "    $_"
            }
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Built image: $imageName"
            }
            else {
                Write-Error "Failed to build image: $imageName"
            }
        }
        else {
            Write-Warning "No Dockerfile found at '$buildPath'. Skipping image build for '$($service.Name)'."
        }
    }

    # Step 3: Load images into minikube
    Write-Section "Loading Images into Minikube"
    foreach ($service in $Services) {
        $imageName = Get-ImageName -Service $service.Name
        if (Test-DockerImageExists -Image $imageName) {
            Write-Info "Loading '$imageName' into minikube..."
            & $MinikubePath image load $imageName 2>&1 | ForEach-Object {
                Write-Host "    $_"
            }
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Loaded image: $imageName"
            }
            else {
                Write-Error "Failed to load image: $imageName"
            }
        }
        else {
            Write-Warning "Image '$imageName' not found locally. Skipping."
        }
    }

    # Step 4: Generate and apply manifests
    Write-Section "Applying Kubernetes Manifests"

    foreach ($env in $Environments) {
        Write-Host ""
        Write-Host "  --- Deploying to: $env ---" -ForegroundColor Yellow

        # Ensure namespace
        Ensure-Namespace -Namespace $Namespaces[$env]

        # Generate manifests for this environment
        $envManifestDir = Join-Path $ManifestDir $env
        if (-not (Test-Path $envManifestDir)) {
            New-Item -ItemType Directory -Path $envManifestDir -Force | Out-Null
        }

        # Generate deployment manifests
        foreach ($service in $Services) {
            $imageName = Get-ImageName -Service $service.Name
            $deployName = Get-DeploymentName -Service $service.Name
            $replicas = if ($env -eq "prod" -and $service.Name -ne "web-ui") { 2 } else { 1 }

            $manifestContent = @"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $deployName
  namespace: $env
  labels:
    app: $deployName
    environment: $env
spec:
  replicas: $replicas
  selector:
    matchLabels:
      app: $deployName
  template:
    metadata:
      labels:
        app: $deployName
        environment: $env
    spec:
      containers:
      - name: $deployName
        image: $imageName
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: $($service.ContainerPort)
          protocol: TCP
        resources:
          requests:
            memory: `"64Mi`"
            cpu: `"50m`"
          limits:
            memory: `"256Mi`"
            cpu: `"500m`"
        livenessProbe:
          httpGet:
            path: /health
            port: $($service.ContainerPort)
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: $($service.ContainerPort)
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: $deployName
  namespace: $env
  labels:
    app: $deployName
    environment: $env
spec:
  type: ClusterIP
  selector:
    app: $deployName
  ports:
  - port: $($service.Port)
    targetPort: $($service.ContainerPort)
    protocol: TCP
    name: http
"@

            $manifestFile = Join-Path $envManifestDir "${deployName}.yaml"
            $manifestContent | Set-Content -Path $manifestFile -Encoding UTF8
            Write-Info "Generated manifest: $deployName for $env"
        }

        # Apply manifests
        Write-Info "Applying manifests to namespace '$env'..."
        $applyOutput = kubectl apply -f $envManifestDir 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Manifests applied to '$env'."
        }
        else {
            Write-Error "Failed to apply manifests to '$env'."
            Write-Host "    $applyOutput" -ForegroundColor Red
        }
    }

    # Step 5: Wait for pods to be ready
    Write-Section "Waiting for Pods to be Ready"
    foreach ($env in $Environments) {
        Write-Info "Waiting for $env pods..."
        $ready = kubectl wait --for=condition=available deployment --all -n $Namespaces[$env] --timeout=120s 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Success "All pods ready in $env."
        }
        else {
            Write-Warning "Timeout waiting for pods in $env. Check status with 'status' command."
        }
    }

    Write-Section "Deployment Complete"
    Write-Success "All environments deployed successfully!"
    Write-Host ""
    Write-Host "  To access services, run:" -ForegroundColor Cyan
    Write-Host "    .\cluster-manager.ps1 port-forward <env> <service> <local-port>" -ForegroundColor Gray
}

# ============================================================
# Command: deploy-env
# ============================================================

function Deploy-Environment {
    param([string]$Env)

    if (-not $Namespaces.ContainsKey($Env)) {
        Write-Error "Invalid environment: '$Env'. Valid environments: $($Environments -join ', ')"
        return
    }

    Write-Section "Deploying to Environment: $Env"

    # Start minikube if not running
    if (-not (Test-MinikubeRunning)) {
        Write-Info "Starting minikube..."
        & $MinikubePath start --driver=docker --memory=4096 --cpus=4 2>&1 | ForEach-Object {
            Write-Host "    $_"
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to start minikube. Aborting deploy."
            exit 1
        }
    }

    Ensure-KubectlContext

    # Build images
    Write-Section "Building Docker Images"
    foreach ($service in $Services) {
        $imageName = Get-ImageName -Service $service.Name
        $buildPath = Join-Path $BaseDir $service.Name
        $dockerfilePath = Join-Path $buildPath "Dockerfile"

        if (Test-Path $dockerfilePath) {
            Write-Info "Building image: $imageName"
            docker build -t $imageName -f $dockerfilePath $buildPath 2>&1 | ForEach-Object {
                Write-Host "    $_"
            }
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Built image: $imageName"
            }
            else {
                Write-Error "Failed to build image: $imageName"
            }
        }
        else {
            Write-Warning "No Dockerfile found at '$buildPath'. Skipping '$($service.Name)'."
        }
    }

    # Load images into minikube
    Write-Section "Loading Images into Minikube"
    foreach ($service in $Services) {
        $imageName = Get-ImageName -Service $service.Name
        if (Test-DockerImageExists -Image $imageName) {
            Write-Info "Loading '$imageName' into minikube..."
            & $MinikubePath image load $imageName 2>&1 | ForEach-Object {
                Write-Host "    $_"
            }
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Loaded image: $imageName"
            }
        }
    }

    # Ensure namespace
    Ensure-Namespace -Namespace $Namespaces[$Env]

    # Generate and apply manifests
    Write-Section "Applying Kubernetes Manifests for $Env"

    $envManifestDir = Join-Path $ManifestDir $Env
    if (-not (Test-Path $envManifestDir)) {
        New-Item -ItemType Directory -Path $envManifestDir -Force | Out-Null
    }

    foreach ($service in $Services) {
        $imageName = Get-ImageName -Service $service.Name
        $deployName = Get-DeploymentName -Service $service.Name
        $replicas = if ($Env -eq "prod" -and $service.Name -ne "web-ui") { 2 } else { 1 }

        $manifestContent = @"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $deployName
  namespace: $Env
  labels:
    app: $deployName
    environment: $Env
spec:
  replicas: $replicas
  selector:
    matchLabels:
      app: $deployName
  template:
    metadata:
      labels:
        app: $deployName
        environment: $Env
    spec:
      containers:
      - name: $deployName
        image: $imageName
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: $($service.ContainerPort)
          protocol: TCP
        resources:
          requests:
            memory: `"64Mi`"
            cpu: `"50m`"
          limits:
            memory: `"256Mi`"
            cpu: `"500m`"
        livenessProbe:
          httpGet:
            path: /health
            port: $($service.ContainerPort)
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: $($service.ContainerPort)
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: $deployName
  namespace: $Env
  labels:
    app: $deployName
    environment: $Env
spec:
  type: ClusterIP
  selector:
    app: $deployName
  ports:
  - port: $($service.Port)
    targetPort: $($service.ContainerPort)
    protocol: TCP
    name: http
"@

        $manifestFile = Join-Path $envManifestDir "${deployName}.yaml"
        $manifestContent | Set-Content -Path $manifestFile -Encoding UTF8
    }

    Write-Info "Applying manifests to namespace '$($Namespaces[$Env])'..."
    $applyOutput = kubectl apply -f $envManifestDir 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Manifests applied to '$Env'."
    }
    else {
        Write-Error "Failed to apply manifests to '$Env'."
        Write-Host "    $applyOutput" -ForegroundColor Red
    }

    # Wait for pods
    Write-Info "Waiting for pods in $Env..."
    $ready = kubectl wait --for=condition=available deployment --all -n $Namespaces[$Env] --timeout=120s 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Success "All pods ready in $Env."
    }
    else {
        Write-Warning "Timeout waiting for pods in $Env. Check status with 'status' command."
    }

    Write-Section "Deployment Complete"
    Write-Success "Environment '$Env' deployed successfully!"
}

# ============================================================
# Command: restart
# ============================================================

function Restart-Service {
    param([string]$Env, [string]$Service)

    if (-not $Namespaces.ContainsKey($Env)) {
        Write-Error "Invalid environment: '$Env'. Valid environments: $($Environments -join ', ')"
        return
    }

    $ns = $Namespaces[$Env]
    $deployName = Get-DeploymentName -Service $Service

    Write-Section "Restarting Service - Environment: $env | Service: $Service"

    # Check namespace
    $nsExists = kubectl get namespace $ns 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Namespace '$ns' does not exist."
        return
    }

    # Check if deployment exists
    $deployExists = kubectl get deployment $deployName -n $ns 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Deployment '$deployName' not found in namespace '$ns'."
        return
    }

    Write-Info "Restarting deployment '$deployName' in namespace '$ns'..."
    kubectl rollout restart deployment/$deployName -n $ns 2>&1 | ForEach-Object {
        Write-Host "    $_"
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Restart initiated for '$deployName' in '$env'."
        Write-Info "Monitor with: kubectl get pods -n $ns -l app=$deployName -w"
    }
    else {
        Write-Error "Failed to restart '$deployName'."
    }
}

# ============================================================
# Command: scale
# ============================================================

function Scale-Deployment {
    param([string]$Env, [string]$Service, [int]$Count)

    if (-not $Namespaces.ContainsKey($Env)) {
        Write-Error "Invalid environment: '$Env'. Valid environments: $($Environments -join ', ')"
        return
    }

    if ($Count -lt 1) {
        Write-Error "Replica count must be at least 1."
        return
    }

    $ns = $Namespaces[$Env]
    $deployName = Get-DeploymentName -Service $Service

    Write-Section "Scaling Service - Environment: $env | Service: $Service | Replicas: $Count"

    # Check namespace
    $nsExists = kubectl get namespace $ns 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Namespace '$ns' does not exist."
        return
    }

    # Check if deployment exists
    $deployExists = kubectl get deployment $deployName -n $ns 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Deployment '$deployName' not found in namespace '$ns'."
        return
    }

    Write-Info "Scaling deployment '$deployName' in namespace '$ns' to $Count replicas..."
    kubectl scale deployment/$deployName -n $ns --replicas=$Count 2>&1 | ForEach-Object {
        Write-Host "    $_"
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Scaled '$deployName' in '$env' to $Count replica(s)."
    }
    else {
        Write-Error "Failed to scale '$deployName'."
    }
}

# ============================================================
# Command: port-forward
# ============================================================

function Start-PortForward {
    param([string]$Env, [string]$Service, [int]$LocalPort)

    if (-not $Namespaces.ContainsKey($Env)) {
        Write-Error "Invalid environment: '$Env'. Valid environments: $($Environments -join ', ')"
        return
    }

    $ns = $Namespaces[$Env]
    $deployName = Get-DeploymentName -Service $Service
    $serviceInfo = $Services | Where-Object { $_.Name -eq $Service } | Select-Object -First 1

    if (-not $serviceInfo) {
        Write-Error "Service '$Service' not found. Valid services: $($Services.Name -join ', ')"
        return
    }

    Write-Section "Port Forwarding - Environment: $env | Service: $Service"
    Write-Host "  Local:  http://localhost:$LocalPort" -ForegroundColor Yellow
    Write-Host "  Remote: $deployName.$ns.svc.cluster.local:$($serviceInfo.Port)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Press Ctrl+C to stop port forwarding." -ForegroundColor DarkGray
    Write-Host ""

    # Get the pod name
    $pods = kubectl get pods -n $ns -l app=$deployName --no-headers 2>&1
    if ($LASTEXITCODE -ne 0 -or -not $pods) {
        Write-Error "No pods found for deployment '$deployName' in namespace '$ns'."
        return
    }

    $podName = ($pods | Where-Object { $_.Trim() })[0] -split '\s+' | Select-Object -First 1
    if (-not $podName) {
        Write-Error "Could not determine pod name."
        return
    }

    Write-Info "Forwarding: $podName -> localhost:$LocalPort"
    Write-Host ""

    kubectl port-forward -n $ns pod/$podName $LocalPort`:``($serviceInfo.ContainerPort) 2>&1 | ForEach-Object {
        Write-Host "    $_"
    }
}

# ============================================================
# Command: clean
# ============================================================

function Clean-Cluster {
    Write-Section "Cleaning Cluster - Deleting All Namespaces"

    # Confirm before deleting
    Write-Host ""
    $confirm = Read-Host "  [CONFIRM] This will delete all namespaces and stop minikube. Continue? (y/n)"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Info "Cleanup cancelled."
        return
    }

    # Delete namespaces
    foreach ($env in $Environments) {
        $ns = $Namespaces[$env]
        Write-Info "Deleting namespace '$ns'..."
        kubectl delete namespace $ns 2>&1 | ForEach-Object {
            Write-Host "    $_"
        }
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Deleted namespace: $ns"
        }
        else {
            Write-Warning "Could not delete namespace '$ns' (may not exist or already deleted)."
        }
    }

    # Stop minikube
    Write-Info "Stopping minikube..."
    if (Test-MinikubeRunning) {
        & $MinikubePath stop 2>&1 | ForEach-Object {
            Write-Host "    $_"
        }
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Minikube stopped."
        }
        else {
            Write-Warning "Could not stop minikube."
        }
    }
    else {
        Write-Info "Minikube was not running."
    }

    # Clean backup directory
    if (Test-Path $BackupDir) {
        Remove-Item -Path $BackupDir -Recurse -Force 2>&1 | Out-Null
        Write-Success "Cleaned backup directory."
    }

    Write-Section "Cleanup Complete"
    Write-Success "All namespaces deleted and minikube stopped."
}

# ============================================================
# Command: backup
# ============================================================

function Backup-Manifests {
    Write-Section "Backing Up All Manifests"

    # Create backup directory
    if (-not (Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    }

    $timestamp = Get-Timestamp
    $backupComplete = $true

    foreach ($env in $Environments) {
        $ns = $Namespaces[$env]

        # Check if namespace exists
        $nsExists = kubectl get namespace $ns 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Namespace '$ns' does not exist. Skipping."
            continue
        }

        # Create per-environment backup directory
        $envBackupDir = Join-Path $BackupDir "manifests_${env}_${timestamp}"
        if (-not (Test-Path $envBackupDir)) {
            New-Item -ItemType Directory -Path $envBackupDir -Force | Out-Null
        }

        Write-Info "Backing up manifests from '$env'..."

        # Backup each deployment
        foreach ($service in $Services) {
            $deployName = Get-DeploymentName -Service $service.Name
            $yamlFile = Join-Path $envBackupDir "${deployName}.yaml"

            # Get the full resource YAML
            $resource = kubectl get $deployName -n $ns -o yaml 2>&1
            if ($LASTEXITCODE -eq 0 -and $resource) {
                $resource | Set-Content -Path $yamlFile -Encoding UTF8
                Write-Info "  Backed up: $deployName -> $yamlFile"
            }
            else {
                Write-Warning "  Could not get resource '$deployName' from '$ns'."
            }
        }

        # Also backup services
        foreach ($service in $Services) {
            $svcName = Get-DeploymentName -Service $service.Name
            $yamlFile = Join-Path $envBackupDir "${svcName}-svc.yaml"

            $svcResource = kubectl get service $svcName -n $ns -o yaml 2>&1
            if ($LASTEXITCODE -eq 0 -and $svcResource) {
                $svcResource | Set-Content -Path $yamlFile -Encoding UTF8
                Write-Info "  Backed up service: $svcName -> $yamlFile"
            }
        }

        # Create manifest list for this environment
        $manifestList = kubectl get all -n $ns 2>&1
        $manifestFile = Join-Path $envBackupDir "manifest-list.txt"
        if ($LASTEXITCODE -eq 0) {
            $manifestList | Set-Content -Path $manifestFile -Encoding UTF8
        }

        # Create configmaps and secrets backup
        $configMaps = kubectl get configmap -n $ns -o yaml 2>&1
        if ($LASTEXITCODE -eq 0 -and $configMaps) {
            $configFile = Join-Path $envBackupDir "configmaps.yaml"
            $configMaps | Set-Content -Path $configFile -Encoding UTF8
        }

        $secrets = kubectl get secret -n $ns -o yaml 2>&1
        if ($LASTEXITCODE -eq 0 -and $secrets) {
            $secretFile = Join-Path $envBackupDir "secrets.yaml"
            $secrets | Set-Content -Path $secretFile -Encoding UTF8
        }

        # Create tar.gz archive
        $backupFileName = Get-BackupFileName -Env $env
        $backupFilePath = Join-Path $BackupDir $backupFileName
        $compressArgs = @{
            Path = $envBackupDir
            DestinationPath = $backupFilePath
            CompressionLevel = "Fastest"
            Force = $true
        }
        Compress-Archive @compressArgs -ErrorAction SilentlyContinue

        if (Test-Path $backupFilePath) {
            Write-Success "Backup created: $backupFileName"
        }
        else {
            Write-Warning "Could not create archive for '$env'."
        }
    }

    Write-Section "Backup Complete"
    Write-Success "All backups saved to: $BackupDir"
    Get-ChildItem $BackupDir -Filter "*.tar.gz" -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "    $($_.Name) ($([math]::Round($_.Length / 1KB)) KB)" -ForegroundColor DarkGray
    }
}

# ============================================================
# Command: restore
# ============================================================

function Restore-Manifests {
    Write-Section "Restoring from Backup"

    if (-not (Test-Path $BackupDir)) {
        Write-Error "Backup directory not found at '$BackupDir'."
        return
    }

    $backups = Get-ChildItem -Path $BackupDir -Filter "*.tar.gz" | Sort-Object LastWriteTime -Descending

    if (-not $backups -or $backups.Count -eq 0) {
        Write-Error "No backup files found in '$BackupDir'."
        return
    }

    Write-Host ""
    Write-Host "  Available backups:" -ForegroundColor Yellow
    Write-Host "  $(('-' * 50))" -ForegroundColor Gray

    for ($i = 0; $i -lt $backups.Count; $i++) {
        $backup = $backups[$i]
        $dateStr = $backup.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
        $sizeStr = "{0:N0}" -f ($backup.Length / 1KB)
        Write-Host "    [$i] $dateStr  $sizeStr KB" -ForegroundColor Cyan
        Write-Host "        $($backup.Name)" -ForegroundColor DarkGray
    }

    Write-Host ""
    $choice = Read-Host "  Select backup to restore (number) or 'a' for latest"

    if ($choice -eq "a" -or $choice -eq "A") {
        $selected = $backups[0]
    }
    else {
        $idx = [int]$choice
        if ($idx -lt 0 -or $idx -ge $backups.Count) {
            Write-Error "Invalid selection."
            return
        }
        $selected = $backups[$idx]
    }

    Write-Host ""
    Write-Host "  Restoring from: $($selected.Name)" -ForegroundColor Yellow

    # Extract backup
    $extractDir = Join-Path $BackupDir "restore_temp_$(Get-Timestamp)"
    New-Item -ItemType Directory -Path $extractDir -Force | Out-Null

    Expand-Archive -Path $selected.FullName -DestinationPath $extractDir -Force

    # Find the manifest directories
    $manifestDirs = Get-ChildItem -Path $extractDir -Directory -Filter "manifests_*"

    if (-not $manifestDirs -or $manifestDirs.Count -eq 0) {
        Write-Error "No manifest directories found in backup."
        Remove-Item -Path $extractDir -Recurse -Force -ErrorAction SilentlyContinue
        return
    }

    foreach ($manifestDir in $manifestDirs) {
        $envName = $manifestDir.Name -replace "manifests_", ""
        # Extract env name (remove timestamp suffix)
        $envName = $envName -replace "_\d{8}_\d{6}", ""

        if (-not $Namespaces.ContainsKey($envName)) {
            Write-Warning "Unknown environment '$envName' in backup. Skipping."
            continue
        }

        $ns = $Namespaces[$envName]

        # Ensure namespace exists
        Ensure-Namespace -Namespace $ns

        # Apply YAML files
        $yamlFiles = Get-ChildItem -Path $manifestDir.FullName -Filter "*.yaml"

        if ($yamlFiles.Count -eq 0) {
            Write-Warning "No YAML files found in backup for '$envName'."
            continue
        }

        Write-Info "Restoring manifests for '$envName'..."

        foreach ($yamlFile in $yamlFiles) {
            # Skip manifest list and metadata files
            $baseName = [System.IO.Path]::GetFileNameWithoutExtension($yamlFile.Name)
            if ($baseName -eq "manifest-list") { continue }

            $content = Get-Content $yamlFile.FullName -Raw
            if (-not $content) { continue }

            # Split multi-document YAML and apply each
            $docs = $content -split "^---\s*$"
            foreach ($doc in $docs) {
                $trimmed = $doc.Trim()
                if (-not $trimmed -or $trimmed -eq "") { continue }
                if ($trimmed -match "^#") { continue }

                # Apply the document
                $tempFile = Join-Path $extractDir "temp_apply_$($yamlFile.BaseName).yaml"
                $trimmed | Set-Content -Path $tempFile -Encoding UTF8
                kubectl apply -f $tempFile 2>&1 | ForEach-Object {
                    Write-Host "    $_"
                }
            }
        }

        Write-Success "Restored manifests for '$envName'."
    }

    # Cleanup temp directory
    Remove-Item -Path $extractDir -Recurse -Force -ErrorAction SilentlyContinue

    Write-Section "Restore Complete"
    Write-Success "Backup restored successfully!"
}

# ============================================================
# Command: health
# ============================================================

function Run-HealthChecks {
    Write-Section "Running Health Checks"

    $allPassed = $true

    foreach ($env in $Environments) {
        $ns = $Namespaces[$env]
        Write-Host ""
        Write-Host "  Environment: $env (namespace: $ns)" -ForegroundColor Yellow
        Write-Host "  $(('-' * 55))" -ForegroundColor Gray

        # Check namespace exists
        $nsExists = kubectl get namespace $ns 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    [FAIL] Namespace '$ns' does not exist." -ForegroundColor Red
            $allPassed = $false
            continue
        }

        foreach ($service in $Services) {
            $deployName = Get-DeploymentName -Service $service.Name
            $checkPassed = $true

            # Check 1: Deployment exists
            $deployExists = kubectl get deployment $deployName -n $ns 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Host "    [$deployName] [FAIL] Deployment not found." -ForegroundColor Red
                $checkPassed = $false
                $allPassed = $false
                continue
            }

            # Check 2: Pod status
            $pods = kubectl get pods -n $ns -l app=$deployName --no-headers 2>&1
            $runningPods = 0
            $errorPods = 0

            if ($LASTEXITCODE -eq 0 -and $pods) {
                foreach ($line in ($pods | Where-Object { $_.Trim() })) {
                    $parts = $line -split '\s+'
                    if ($parts.Count -ge 3) {
                        $status = $parts[1]
                        if ($status -eq "Running") { $runningPods++ }
                        elseif ($status -eq "Error" -or $status -eq "CrashLoopBackOff") { $errorPods++ }
                    }
                }
            }

            # Check 3: Service exists
            $svcExists = kubectl get service $deployName -n $ns 2>&1 | Out-Null
            $svcStatus = if ($LASTEXITCODE -eq 0) { "OK" } else { "MISSING" }

            # Check 4: Readiness probe
            $readyCondition = kubectl get deployment $deployName -n $ns -o json 2>$null | ConvertFrom-Json -ErrorAction SilentlyContinue
            $isReady = $false
            if ($readyCondition) {
                $conditions = $readyCondition.Status.Conditions
                $availableCond = $conditions | Where-Object { $_.Type -eq "Available" }
                if ($availableCond) {
                    $isReady = $availableCond.Status -eq "True"
                }
            }

            # Display results
            if ($errorPods -gt 0) {
                Write-Host "    [$deployName] [FAIL] Pods: $runningPods Running, $errorPods Error" -ForegroundColor Red
                $checkPassed = $false
                $allPassed = $false
            }
            elseif ($runningPods -eq 0) {
                Write-Host "    [$deployName] [WARN] No running pods (0 Running)" -ForegroundColor Yellow
            }
            else {
                $statusStr = if ($isReady) { "[OK]" } else { "[DEGRADED]" }
                $color = if ($isReady) { [ConsoleColor]::Green } else { [ConsoleColor]::Yellow }
                Write-Host "    [$deployName] $statusStr Pods: $runningPods Running | Service: $svcStatus | Port: $($service.Port)" -ForegroundColor $color
            }
        }

        # Check resource usage for this namespace
        Write-Host ""
        Write-Host "    Resource Usage:" -ForegroundColor Gray
        $resourceOutput = kubectl top pods -n $ns 2>&1
        if ($LASTEXITCODE -eq 0 -and $resourceOutput) {
            foreach ($line in $resourceOutput) {
                if ($line.Trim()) {
                    Write-Host "      $line" -ForegroundColor DarkGray
                }
            }
        }
        else {
            Write-Host "      (metrics not available - ensure metrics-server is running)" -ForegroundColor DarkGray
        }

        Write-Host ""
    }

    # Final summary
    Write-Section "Health Check Summary"
    if ($allPassed) {
        Write-Success "All health checks passed!"
    }
    else {
        Write-Warning "Some health checks failed. Review the output above."
    }
}

# ============================================================
# Command: help
# ============================================================

function Show-Help {
    Write-Box "  Cluster Manager v$ScriptVersion" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Usage: .\cluster-manager.ps1 <command> [args...]" -ForegroundColor White
    Write-Host ""
    Write-Host "  Commands:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "    start                                    Start minikube if not running" -ForegroundColor White
    Write-Host "    stop                                     Stop minikube" -ForegroundColor White
    Write-Host "    status                                   Show pod status for all 3 environments" -ForegroundColor White
    Write-Host "    logs <env> <service>                     Show logs for a service in an environment" -ForegroundColor White
    Write-Host "    deploy                                   Rebuild images, load to minikube, deploy to all envs" -ForegroundColor White
    Write-Host "    deploy-env <env>                         Deploy to a single environment" -ForegroundColor White
    Write-Host "    restart <env> <service>                  Restart a specific service" -ForegroundColor White
    Write-Host "    scale <env> <service> <count>            Scale a deployment to N replicas" -ForegroundColor White
    Write-Host "    port-forward <env> <service> <local-port> Forward port for local access" -ForegroundColor White
    Write-Host "    clean                                    Delete all namespaces and stop minikube" -ForegroundColor White
    Write-Host "    backup                                   Backup all manifests from all namespaces" -ForegroundColor White
    Write-Host "    restore                                  Restore from latest backup" -ForegroundColor White
    Write-Host "    health                                   Run health checks on all services" -ForegroundColor White
    Write-Host "    help                                     Show this help message" -ForegroundColor White
    Write-Host ""
    Write-Host "  Environments: dev, staging, prod" -ForegroundColor Gray
    Write-Host "  Services: task-service, notification-service, web-ui, db" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Examples:" -ForegroundColor Yellow
    Write-Host "    .\cluster-manager.ps1 start" -ForegroundColor DarkGray
    Write-Host "    .\cluster-manager.ps1 deploy" -ForegroundColor DarkGray
    Write-Host "    .\cluster-manager.ps1 deploy-env dev" -ForegroundColor DarkGray
    Write-Host "    .\cluster-manager.ps1 status" -ForegroundColor DarkGray
    Write-Host "    .\cluster-manager.ps1 logs dev task-service" -ForegroundColor DarkGray
    Write-Host "    .\cluster-manager.ps1 restart prod db" -ForegroundColor DarkGray
    Write-Host "    .\cluster-manager.ps1 scale staging task-service 3" -ForegroundColor DarkGray
    Write-Host "    .\cluster-manager.ps1 port-forward dev web-ui 8080" -ForegroundColor DarkGray
    Write-Host "    .\cluster-manager.ps1 backup" -ForegroundColor DarkGray
    Write-Host "    .\cluster-manager.ps1 restore" -ForegroundColor DarkGray
    Write-Host "    .\cluster-manager.ps1 health" -ForegroundColor DarkGray
    Write-Host "    .\cluster-manager.ps1 clean" -ForegroundColor DarkGray
    Write-Host "    .\cluster-manager.ps1 help" -ForegroundColor DarkGray
    Write-Host ""
}

# ============================================================
# Main entry point
# ============================================================

function Main {
    # Check for PowerShell version
    if ($PSVersionTable.PSVersion.Major -lt 5) {
        Write-Error "PowerShell 5.1 or higher is required. Current version: $($PSVersionTable.PSVersion)"
        exit 1
    }

    # Check for kubectl
    if (-not (Test-Command "kubectl")) {
        Write-Error "kubectl is not installed or not in PATH. Install it first."
        exit 1
    }

    # Check for docker
    if (-not (Test-Command "docker")) {
        Write-Error "Docker is not installed or not in PATH. Install it first."
        exit 1
    }

    # Check for minikube
    if (-not (Test-Path $MinikubePath)) {
        Write-Error "Minikube not found at '$MinikubePath'. Please install minikube."
        exit 1
    }

    # Parse arguments
    $args = $args | Where-Object { $_ -ne $null }
    $command = if ($args.Count -gt 0) { $args[0].ToLower() } else { "" }

    switch ($command) {
        "start" {
            Start-Cluster
        }
        "stop" {
            Stop-Cluster
        }
        "status" {
            Show-Status
        }
        "logs" {
            if ($args.Count -lt 3) {
                Write-Error "Usage: cluster-manager.ps1 logs <env> <service>"
                Write-Host ""
                Write-Host "  Environments: dev, staging, prod" -ForegroundColor Gray
                Write-Host "  Services: task-service, notification-service, web-ui, db" -ForegroundColor Gray
                exit 1
            }
            Show-Logs -Env $args[1] -Service $args[2]
        }
        "deploy" {
            Deploy-All
        }
        "deploy-env" {
            if ($args.Count -lt 2) {
                Write-Error "Usage: cluster-manager.ps1 deploy-env <env>"
                Write-Host ""
                Write-Host "  Environments: dev, staging, prod" -ForegroundColor Gray
                exit 1
            }
            Deploy-Environment -Env $args[1]
        }
        "restart" {
            if ($args.Count -lt 3) {
                Write-Error "Usage: cluster-manager.ps1 restart <env> <service>"
                Write-Host ""
                Write-Host "  Environments: dev, staging, prod" -ForegroundColor Gray
                Write-Host "  Services: task-service, notification-service, web-ui, db" -ForegroundColor Gray
                exit 1
            }
            Restart-Service -Env $args[1] -Service $args[2]
        }
        "scale" {
            if ($args.Count -lt 4) {
                Write-Error "Usage: cluster-manager.ps1 scale <env> <service> <count>"
                Write-Host ""
                Write-Host "  Environments: dev, staging, prod" -ForegroundColor Gray
                Write-Host "  Services: task-service, notification-service, web-ui, db" -ForegroundColor Gray
                exit 1
            }
            $count = 0
            if (-not [int]::TryParse($args[3], [ref]$count)) {
                Write-Error "Replica count must be a valid integer."
                exit 1
            }
            Scale-Deployment -Env $args[1] -Service $args[2] -Count $count
        }
        "port-forward" {
            if ($args.Count -lt 4) {
                Write-Error "Usage: cluster-manager.ps1 port-forward <env> <service> <local-port>"
                Write-Host ""
                Write-Host "  Environments: dev, staging, prod" -ForegroundColor Gray
                Write-Host "  Services: task-service, notification-service, web-ui, db" -ForegroundColor Gray
                exit 1
            }
            $port = 0
            if (-not [int]::TryParse($args[3], [ref]$port)) {
                Write-Error "Local port must be a valid integer."
                exit 1
            }
            Start-PortForward -Env $args[1] -Service $args[2] -LocalPort $port
        }
        "clean" {
            Clean-Cluster
        }
        "backup" {
            Backup-Manifests
        }
        "restore" {
            Restore-Manifests
        }
        "health" {
            Run-HealthChecks
        }
        "help" {
            Show-Help
        }
        "" {
            Show-Help
        }
        default {
            Write-Error "Unknown command: '$command'"
            Write-Host ""
            Write-Host "Run 'cluster-manager.ps1 help' for usage information." -ForegroundColor Gray
            exit 1
        }
    }
}

# Run the script
Main
