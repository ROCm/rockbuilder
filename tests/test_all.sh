#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR

# Declare an array of shell script paths
scripts=(
    "./test1_check_build_steps.sh"
    "./test2_incorrect_exec_dir.sh"
    "./test3_correct_exec_dir.sh"
)

# Loop through each script in the array and execute it
for script_path in "${scripts[@]}"; do
    echo "Executing: $script_path"
    # Use 'bash' to explicitly execute the script, or just "$script_path" if it's executable
    bash "$script_path"
    # Check the exit status of the executed script
    if [ $? -ne 0 ]; then
        echo "Error executing $script_path. Exiting."
        exit 1
    fi
done

echo "All scripts executed successfully."
