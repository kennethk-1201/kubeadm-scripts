#!/bin/bash

# Set up cluster
vagrant up

# Enter the master
vagrant ssh master

# Somehow get this output and pass it to the workers
sudo kubeadm token create --print-join-command > connect.sh

logout

# Connect node01
vagrant ssh node01

sudo ./connect.sh

logout

# Connect node02
vagrant ssh node02

sudo ./connect.sh

logout
