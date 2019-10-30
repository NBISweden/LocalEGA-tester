#!/bin/sh

test_file=$(date +"%Y-%m-%d_%H-%M-%S")

if [ "$SIZE" = 'small' ]; then
    fallocate -l 10m /volume/"$test_file"
elif [ "$SIZE" = "medium" ]; then
    fallocate -l 2g /volume/"$test_file"
elif [ "$SIZE" = "large" ]; then
    fallocate -l 80g /volume/"$test_file"
else
    echo "file size not set"
    exit 1
fi

if [ -d "/etc/ssl/certs/ca-certificates.crt" ]; then
  cat /conf/root.ca.crt /etc/ssl/certs/ca-certificates.crt > /volume/ca-certificates

fi

sleep 3
legatest /volume/"$test_file" /conf/config.yaml