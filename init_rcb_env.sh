#!/usr/bin/env bash

VENV_NAME=.venv
LAUNCH_DIR=$(pwd)
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR

echo "The current directory is: $LAUNCH_DIR"
echo "Script directory is: $SCRIPT_DIR"

# Check that this script is called as sourced.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "ERROR: This script must be sourced, not executed!" >&2
    echo "Example:" >&2
    echo "source ./init_rcb_env.sh" >&2
    exit 1
fi

if [ ! -z "$VIRTUAL_ENV" ]; then
    echo "Python virtual environment used: $VIRTUAL_ENV"
else
    if [ ! -f ./.venv/bin/activate ]; then
        echo "Creating python virtual environment: $VENV_NAME"
        python3 -m venv .venv
        echo "Activating python virtual environment: $VENV_NAME"
        source .venv/bin/activate
        pip3 install --upgrade pip
        pip3 install -r requirements.txt
        echo "Python virtual environment created and enabled: $VIRTUAL_ENV"
    else
        source .venv/bin/activate
        echo "Python virtual environment enabled: $VIRTUAL_ENV"
    fi
fi
cd ${LAUNCH_DIR}
