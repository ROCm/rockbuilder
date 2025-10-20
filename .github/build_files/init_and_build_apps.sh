#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR
cd ../..

if [[ -n "$VIRTUAL_ENV" ]]; then
    echo "Virtual environment is active: $VIRTUAL_ENV"
else
     echo "No virtual environment is active."
     source ./init_rcb_env.sh
fi

./rockbuilder.py apps/therock.cfg
if [ ! $? -eq 0 ]; then
    echo ""
    echo "Failed to build therock"
    exit 1
fi

./rockbuilder.py apps/pytorch_28_amd.apps
if [ ! $? -eq 0 ]; then
    echo ""
    echo "Failed to build apps/pytorch_28_amd.apps"
    exit 1
fi


