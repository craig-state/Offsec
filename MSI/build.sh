#!/bin/bash

set -e

OUT="output/AddLocalAdminTest.msi"

mkdir -p output

rm -f "$OUT"

msibuild "$OUT" \
    -i tables/Property.idt \
    -i tables/Directory.idt \
    -i tables/Component.idt \
    -i tables/Feature.idt \
    -i tables/FeatureComponents.idt \
    -i tables/CustomAction.idt \
    -i tables/InstallExecuteSequence.idt

echo "Created: $OUT"
