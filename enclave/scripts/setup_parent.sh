#!/bin/bash
#
# EC2 Parent Instance Setup
# Configures the parent EC2 instance to communicate with the enclave
#

set -e

echo "=========================================="
echo "Setting up EC2 Parent Instance"
echo "=========================================="

# Install vsock-proxy for communication
echo "[1/4] Installing vsock-proxy..."
sudo yum install -y aws-nitro-enclaves-cli || \
    sudo apt-get install -y aws-nitro-enclaves-cli

# Configure vsock-proxy
echo "[2/4] Configuring vsock-proxy..."
sudo mkdir -p /etc/nitro_enclaves
sudo tee /etc/nitro_enclaves/vsock-proxy.yaml > /dev/null <<'EOF'
{
  "proxy": {
    "services": [
      {
        "name": "esg-audit",
        "port": 5005,
        "cid": 3
      }
    ]
  }
}
EOF

# Start vsock-proxy service
echo "[3/4] Starting vsock-proxy..."
sudo systemctl enable nitro-enclaves-vsock-proxy
sudo systemctl start nitro-enclaves-vsock-proxy

# Configure parent application to route requests
echo "[4/4] Setting up parent application..."

# Create systemd service for parent application
sudo tee /etc/systemd/system/esg-audit-parent.service > /dev/null <<'EOF'
[Unit]
Description=ESG Audit Parent Service
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/esg-audit
ExecStart=/opt/esg-audit/venv/bin/python -m enclave.parent_proxy
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable esg-audit-parent

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Build the enclave: ./enclave/scripts/build_enclave.sh"
echo "2. Deploy the enclave: ./enclave/scripts/deploy_enclave.sh"
echo "3. Start parent service: sudo systemctl start esg-audit-parent"
