#!/bin/bash

set -e 

Files=(
    'frontend/node_modules'
)

for file in "${Files[@]}"; do
	rm -rf $file
done
