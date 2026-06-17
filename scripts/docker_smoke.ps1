param(
    [string]$ImageName = "samrat-course-mcp-smoke",
    [string]$ContainerName = "samrat-course-mcp-smoke",
    [string]$Token = "smoke-test-token"
)

$ErrorActionPreference = "Stop"

docker build -t $ImageName .

$existing = docker ps -aq --filter "name=^$ContainerName$"
if ($existing) {
    docker rm -f $ContainerName | Out-Null
}

docker run -d --rm `
    --name $ContainerName `
    -e MCP_API_TOKEN=$Token `
    -e MCP_HOST=0.0.0.0 `
    -e MCP_PORT=8777 `
    -p 127.0.0.1:8777:8777 `
    $ImageName | Out-Null

try {
    Start-Sleep -Seconds 5
    docker exec $ContainerName python -m course_mcp_server.healthcheck | Out-Null
    Write-Output "Docker smoke passed"
}
finally {
    docker rm -f $ContainerName | Out-Null
}
