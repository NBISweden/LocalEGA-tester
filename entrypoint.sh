#!/bin/sh

test_file=$(date +"%Y-%m-%d_%H-%M-%S")

if [ "$SIZE" = 'small' ]; then
    fallocate -l 10m /volume/"$test_file"
elif [ "$SIZE" = "medium" ]; then
    fallocate -l 2g /volume/"$test_file"
elif [ "$SIZE" = "large" ]; then
    fallocate -l 10g /volume/"$test_file"
elif [ "$SIZE" = "xlarge" ]; then
    fallocate -l 25g /volume/"$test_file"
elif [ "$SIZE" = "xxlarge" ]; then
    fallocate -l 50g /volume/"$test_file"
else
    echo "file size not set"
    exit 1
fi

if [ -f "/etc/ssl/certs/ca-certificates.crt" ]; then
  cat /conf/root.ca.crt /etc/ssl/certs/ca-certificates.crt > /volume/ca-certificates

fi

sleep 3
legaenc /volume/"$test_file" /conf/config.yaml
legatest /conf/config.yaml