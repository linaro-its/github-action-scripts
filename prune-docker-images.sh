#!/bin/bash
#
# Remove all linaroits images that are NOT tagged "latest".
#
# Get all of the linaroits images
images=$(docker images --filter=reference="linaroits/*" -q | uniq)
# Get all of the latest images
latest=$(docker images --filter=reference="*/*:latest" -q | uniq)
# Get the differences
prune=$(comm -23 <(echo "$images"|sort) <(echo "$latest"|sort))
for i in $prune
do
    echo "Removing image $i"
    docker rmi -f "$i"
done
#
# Now remove any dangling images. These typically occur when
# the exitautomation image is rebuilt as there can only ever
# be one version of that.
prune=$(docker images -f "dangling=true" -q)
for i in $prune
do
    echo "Removing image $i"
    docker rmi -f "$i"
done
