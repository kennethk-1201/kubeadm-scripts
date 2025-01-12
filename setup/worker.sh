#!/bin/bash

set -euxo pipefail

# Join the cluster using the saved command
sudo bash /vagrant/setup/join.sh
