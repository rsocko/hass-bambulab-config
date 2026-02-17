#!/bin/bash
# Deployment script for Obico ML Server on server-mini
# Usage: ./deploy.sh

set -e  # Exit on error

echo "==================================="
echo "Obico ML Server Deployment Script"
echo "==================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}!${NC} $1"
}

print_info() {
    echo "→ $1"
}

# Check if docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi
print_success "Docker is installed"

# Check if docker compose is available
if ! docker compose version &> /dev/null; then
    print_error "Docker Compose is not available. Please install Docker Compose."
    exit 1
fi
print_success "Docker Compose is available"

# Check if running on correct host
print_info "Checking hostname..."
HOSTNAME=$(hostname)
echo "Current hostname: $HOSTNAME"

read -p "Is this server-mini? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "This script should be run on server-mini. Continue anyway? (y/n): "
    read -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Deployment cancelled."
        exit 0
    fi
fi

# Check available memory
print_info "Checking system resources..."
TOTAL_MEM=$(free -g | awk '/^Mem:/{print $2}')
if [ "$TOTAL_MEM" -lt 4 ]; then
    print_warning "System has less than 4GB RAM ($TOTAL_MEM GB). Obico may not perform optimally."
    read -p "Continue anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Deployment cancelled."
        exit 0
    fi
else
    print_success "System has sufficient RAM ($TOTAL_MEM GB)"
fi

# Check if .env exists
if [ -f .env ]; then
    print_warning ".env file already exists."
    read -p "Do you want to regenerate it? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        mv .env .env.backup
        print_info "Backed up existing .env to .env.backup"
    else
        print_info "Using existing .env file"
        ENV_EXISTS=true
    fi
fi

# Create .env if it doesn't exist
if [ "$ENV_EXISTS" != "true" ]; then
    print_info "Creating .env file..."
    
    # Generate random token
    if command -v openssl &> /dev/null; then
        TOKEN=$(openssl rand -hex 32)
    else
        print_error "OpenSSL not found. Cannot generate secure token."
        print_warning "Please install OpenSSL or manually create .env file with a secure token."
        echo "Example .env file:"
        echo "ML_API_TOKEN=your_secure_random_token_here"
        echo "TZ=America/New_York"
        exit 1
    fi
    
    # Get timezone
    if [ -f /etc/timezone ]; then
        TZ=$(cat /etc/timezone)
    else
        TZ="America/New_York"
        print_warning "Could not detect timezone. Using $TZ"
    fi
    
    cat > .env << EOF
# Obico ML Server Configuration
# Generated on $(date)

# API Token for authentication
ML_API_TOKEN=$TOKEN

# Timezone
TZ=$TZ
EOF
    
    print_success "Created .env file with random API token"
    echo ""
    echo "IMPORTANT: API token has been saved to .env file"
    echo "=========================================="
    echo "You can retrieve it later with:"
    echo "  cat .env | grep ML_API_TOKEN"
    echo "=========================================="
    echo ""
    read -p "Press Enter to continue..."
fi

# Check if port 3333 is in use
print_info "Checking if port 3333 is available..."
if netstat -tuln 2>/dev/null | grep -q ":3333 " || ss -tuln 2>/dev/null | grep -q ":3333 "; then
    print_error "Port 3333 is already in use!"
    echo "Check what's using it: sudo netstat -tulpn | grep 3333"
    exit 1
fi
print_success "Port 3333 is available"

# Pull the Docker image
print_info "Pulling Docker image (this may take a few minutes)..."
if docker compose pull; then
    print_success "Docker image pulled successfully"
else
    print_error "Failed to pull Docker image"
    exit 1
fi

# Start the container
print_info "Starting Obico ML Server..."
if docker compose up -d; then
    print_success "Container started successfully"
else
    print_error "Failed to start container"
    exit 1
fi

# Wait for container to be healthy
print_info "Waiting for container to become healthy..."
RETRY=0
MAX_RETRY=30
while [ $RETRY -lt $MAX_RETRY ]; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' obico-ml-server 2>/dev/null || echo "starting")
    if [ "$STATUS" = "healthy" ]; then
        print_success "Container is healthy!"
        break
    fi
    echo -n "."
    sleep 2
    RETRY=$((RETRY+1))
done
echo ""

if [ $RETRY -eq $MAX_RETRY ]; then
    print_warning "Container did not become healthy within expected time."
    print_info "Check status with: docker compose ps"
    print_info "Check logs with: docker compose logs"
fi

# Test the endpoint
print_info "Testing health endpoint..."
if curl -f -s http://localhost:3333/health > /dev/null 2>&1; then
    print_success "Health endpoint is responding"
else
    print_warning "Health endpoint not responding yet. May need more time to start."
fi

# Display status
echo ""
echo "==================================="
echo "Deployment Summary"
echo "==================================="
docker compose ps
echo ""

# Display resource usage
print_info "Current resource usage:"
docker stats obico-ml-server --no-stream
echo ""

# Display configuration info
echo "==================================="
echo "Configuration Information"
echo "==================================="
echo "API Token: <stored in .env file - use: cat .env | grep ML_API_TOKEN>"
echo "Timezone: $(grep TZ .env | cut -d= -f2)"
echo "Port: 3333"
echo "Health Endpoint: http://$(hostname):3333/health"
echo ""

# Next steps
echo "==================================="
echo "Next Steps"
echo "==================================="
echo "1. Configure Home Assistant integration:"
echo "   - Settings → Devices & Services → Add Integration"
echo "   - Search: Bambu Lab P1 - Spaghetti Detection"
echo "   - Host: http://$(hostname):3333"
echo "   - Token: Run 'cat .env | grep ML_API_TOKEN | cut -d= -f2' to retrieve"
echo ""
echo "2. Import and configure automation blueprint"
echo "   See QUICK_START.md for details"
echo ""
echo "3. Monitor the service:"
echo "   - docker compose logs -f"
echo "   - docker stats obico-ml-server"
echo ""
echo "For troubleshooting, see TROUBLESHOOTING.md"
echo "==================================="

print_success "Deployment complete!"
